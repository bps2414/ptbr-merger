import sys
from datetime import datetime, timezone

import requests
from loguru import logger

from src.config import get_config

config = get_config()

logger.remove()

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

logger.add(
    sys.stdout,
    level=config.logging.level,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
)

if config.logging.file:
    import os

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    log_path = os.path.join(base_dir, config.logging.file)
    logger.add(
        log_path,
        level=config.logging.level,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
        rotation="10 MB",
        retention="5 days",
        encoding="utf-8",
    )

info = logger.info
error = logger.error
warning = logger.warning
success = logger.success
debug = logger.debug

_PHASE_META = {
    "search": {"label": "Buscando release PT-BR", "progress": 12, "eta_label": "Estimando"},
    "inject": {"label": "Enviando para o qBittorrent", "progress": 22, "eta_label": "Aguardando fila"},
    "download-await": {"label": "Aguardando dual audio", "progress": 35, "eta_label": "Depende dos seeders"},
    "merge-start": {"label": "Preparando merge", "progress": 45, "eta_label": "Iniciando análise"},
    "extract": {"label": "Extraindo áudio PT-BR", "progress": 58, "eta_label": "Poucos instantes"},
    "mux": {"label": "Muxando arquivo 4K", "progress": 78, "eta_label": "Pode levar alguns minutos"},
    "validate": {"label": "Validando MKV final", "progress": 90, "eta_label": "Quase concluído"},
    "finalize": {"label": "Atualizando Radarr e limpeza", "progress": 96, "eta_label": "Instantes"},
}

_STATUS_VISUALS = {
    "PROGRESS": {"icon": "🎬", "label": "Sessão em andamento"},
    "SUCCESS": {"icon": "✅", "label": "Merge concluído"},
    "SKIPPED_HAS_PTBR": {"icon": "🎞️", "label": "Otimização direta"},
    "NOT_FOUND": {"icon": "🔎", "label": "Sem dual compatível"},
    "NOT_FOUND_STREAM": {"icon": "🎧", "label": "Faixa PT-BR ausente"},
    "SYNC_MISMATCH": {"icon": "⏱️", "label": "Sync incompatível"},
    "RUNTIME_INCOMPATIBLE": {"icon": "📏", "label": "Runtime incompatível"},
    "OFFSET_SUSPECTED": {"icon": "🎚️", "label": "Offset suspeito"},
    "DUPLICATE_CALL": {"icon": "🌀", "label": "Execução duplicada"},
    "ABANDONED": {"icon": "🛑", "label": "Fluxo abandonado"},
    "ERROR": {"icon": "💥", "label": "Falha no pipeline"},
}


def _movie_name(context: dict) -> str:
    title = context.get("title", "Título Desconhecido")
    year = context.get("year", "")
    return f"{title} ({year})" if year else title


def _tmdb_url(context: dict) -> str | None:
    tmdb_id = context.get("tmdbId")
    if tmdb_id:
        return f"https://www.themoviedb.org/movie/{tmdb_id}"
    return None


def _format_duration(seconds: float | int | None) -> str:
    if seconds in (None, "", 0):
        return "N/A"
    total_seconds = int(float(seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    if minutes:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"


def _progress_bar(percent: int) -> str:
    filled = max(0, min(10, round(percent / 10)))
    return "█" * filled + "░" * (10 - filled)


def _status_label(status: str) -> str:
    labels = {
        "PROGRESS": "Em andamento",
        "SUCCESS": "Concluído",
        "SKIPPED_HAS_PTBR": "Otimização local",
        "NOT_FOUND": "Sem dual compatível",
        "NOT_FOUND_STREAM": "Faixa PT-BR ausente",
        "SYNC_MISMATCH": "Sync incompatível",
        "RUNTIME_INCOMPATIBLE": "Runtime incompatível",
        "OFFSET_SUSPECTED": "Offset suspeito",
        "DUPLICATE_CALL": "Execução duplicada",
        "ABANDONED": "Abandonado",
        "ERROR": "Erro",
    }
    return labels.get(status, status.title())


def _status_visual(status: str) -> dict:
    return _STATUS_VISUALS.get(status, {"icon": "🎬", "label": _status_label(status)})


def _phase_meta(phase: str | None, status: str) -> dict:
    if phase and phase in _PHASE_META:
        return _PHASE_META[phase]
    if status == "SUCCESS":
        return {"label": "Processo finalizado", "progress": 100, "eta_label": "Concluído"}
    if status in {"ERROR", "ABANDONED"}:
        return {"label": "Execução interrompida", "progress": 100, "eta_label": "Encerrado"}
    return {"label": "Atualização de status", "progress": 0, "eta_label": "N/A"}


def _diagnostic_summary(context: dict) -> str:
    parts = []
    if context.get("diff") is not None:
        parts.append(f"sync {float(context['diff']):.3f}s")
    if context.get("offset_estimate") is not None:
        parts.append(f"offset {float(context['offset_estimate']):.3f}s")
    if context.get("validation_reason"):
        parts.append(f"validação {context['validation_reason']}")
    return " • ".join(parts) if parts else "Sem anomalias detectadas até aqui"


def notify_status(status: str, context: dict) -> None:
    """
    Registra no log e envia notificação para o Discord.
    """
    message = _build_message(status, context)

    if status in ("SUCCESS", "SKIPPED_HAS_PTBR", "DUPLICATE_CALL"):
        info(message)
    elif status in ("NOT_FOUND", "NOT_FOUND_STREAM", "SYNC_MISMATCH", "RUNTIME_INCOMPATIBLE", "OFFSET_SUSPECTED", "ABANDONED"):
        warning(message)
    elif status == "ERROR":
        error(message)
    else:
        warning(message)

    message_id = _send_discord_webhook(status, context)
    if message_id:
        context["discord_message_id"] = message_id


def _build_message(status: str, context: dict) -> str:
    movie_name = _movie_name(context)

    if status == "SUCCESS":
        return f"SUCCESS: Áudio PT-BR injetado com sucesso no filme {movie_name}"
    if status == "SKIPPED_HAS_PTBR":
        return f"SKIPPED: O filme {movie_name} já possui faixa de áudio PT-BR."
    if status == "NOT_FOUND":
        return f"NOT_FOUND: Nenhuma versão PT-BR aceitável encontrada para o filme {movie_name}."
    if status == "NOT_FOUND_STREAM":
        return f"NOT_FOUND_STREAM: Versão baixada, mas stream de idioma 'por' ausente em {movie_name}."
    if status == "SYNC_MISMATCH":
        diff = context.get("diff", "Desconhecida")
        return f"SYNC_MISMATCH: Diferença de duração muito grande ({diff}s) detectada para {movie_name}."
    if status == "RUNTIME_INCOMPATIBLE":
        diff = context.get("diff", "Desconhecida")
        return f"RUNTIME_INCOMPATIBLE: o candidato diverge estruturalmente do runtime esperado ({diff}s) para {movie_name}."
    if status == "OFFSET_SUSPECTED":
        diff = context.get("diff", "Desconhecida")
        return f"OFFSET_SUSPECTED: desvio temporal detectado ({diff}s) para {movie_name}, mas sem correção automática nesta fase."
    if status == "DUPLICATE_CALL":
        return f"DUPLICATE_CALL: Trigger abortado; processo já estava em andamento para {movie_name}."
    if status == "ABANDONED":
        return f"ABANDONED: Limite de tentativas atingido para {movie_name}."
    if status == "ERROR":
        err_msg = context.get("error", "Erro não especificado")
        return f"ERROR: Falha processando {movie_name} - {err_msg}"
    return f"Status desconhecido '{status}' para o filme {movie_name}"


def _build_embed_payload(status: str, context: dict, phase: str | None = None) -> dict:
    colors = {
        "SUCCESS": 0x22C55E,
        "SKIPPED_HAS_PTBR": 0x64748B,
        "DUPLICATE_CALL": 0x64748B,
        "NOT_FOUND": 0xF59E0B,
        "NOT_FOUND_STREAM": 0xF59E0B,
        "SYNC_MISMATCH": 0xF97316,
        "RUNTIME_INCOMPATIBLE": 0xF97316,
        "OFFSET_SUSPECTED": 0xF97316,
        "ABANDONED": 0xEF4444,
        "ERROR": 0xDC2626,
        "PROGRESS": 0x2563EB,
    }

    phase_info = _phase_meta(phase, status)
    visual = _status_visual(status)
    progress_percent = int(context.get("progress_percent", phase_info["progress"]))
    eta_text = _format_duration(context.get("eta_seconds")) if context.get("eta_seconds") is not None else phase_info["eta_label"]
    runtime_text = _format_duration(context.get("process_runtime"))

    fields = [
        {"name": "Status", "value": _status_label(status), "inline": True},
        {"name": "Fase", "value": phase_info["label"], "inline": True},
        {"name": "Progresso", "value": f"`{_progress_bar(progress_percent)}` {progress_percent}%", "inline": False},
        {"name": "ETA", "value": eta_text, "inline": True},
        {"name": "Tempo decorrido", "value": runtime_text, "inline": True},
        {"name": "Diagnóstico", "value": _diagnostic_summary(context), "inline": False},
    ]

    if context.get("release_title"):
        fields.append({"name": "Release", "value": str(context["release_title"])[:1024], "inline": False})
    if context.get("indexer"):
        fields.append({"name": "Indexer", "value": str(context["indexer"]), "inline": True})
    if context.get("candidate_index") is not None:
        fields.append({"name": "Candidato", "value": str(context["candidate_index"]), "inline": True})
    if context.get("score") is not None:
        fields.append({"name": "Score", "value": str(context["score"]), "inline": True})
    if context.get("diff") is not None:
        fields.append({"name": "Sync diff", "value": f"{float(context['diff']):.3f}s", "inline": True})
    if context.get("offset_estimate") is not None:
        fields.append({"name": "Offset estimado", "value": f"{float(context['offset_estimate']):.3f}s", "inline": True})

    embed = {
        "author": {"name": f"{visual['icon']} {visual['label']}"},
        "title": _movie_name(context),
        "description": f"**{_build_message(status, context)}**",
        "color": colors.get(status, 0x64748B),
        "fields": fields,
        "footer": {"text": f"PTBRMerger • TMDB {context.get('tmdbId', 'N/A')}"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    tmdb_url = _tmdb_url(context)
    if tmdb_url:
        embed["url"] = tmdb_url

    poster_url = context.get("poster_url")
    if poster_url:
        embed["thumbnail"] = {"url": poster_url}

    backdrop_url = context.get("backdrop_url")
    if backdrop_url:
        embed["image"] = {"url": backdrop_url}

    return {
        "username": getattr(config.notifications, "username", "PTBRMerger Bot"),
        "embeds": [embed],
    }


def send_progress_update(phase: str, context: dict, message_id: str | None = None) -> str | None:
    webhook_url = config.notifications.discord_webhook_url
    if not webhook_url or not str(webhook_url).strip():
        debug("Discord Webhook desativado no config.yml. Pulando atualização de progresso.")
        return message_id

    payload = _build_embed_payload("PROGRESS", context, phase=phase)

    try:
        if message_id:
            response = requests.patch(f"{webhook_url}/messages/{message_id}", json=payload, timeout=5)
            response.raise_for_status()
            body = response.json() if hasattr(response, "json") else {}
            return body.get("id", message_id)

        response = requests.post(webhook_url, params={"wait": "true"}, json=payload, timeout=5)
        response.raise_for_status()
        body = response.json() if hasattr(response, "json") else {}
        return body.get("id")
    except Exception as exc:
        error(f"Falha ao atualizar progresso no Discord: {exc}")
        return message_id


def _send_discord_webhook(status: str, context: dict) -> str | None:
    webhook_url = config.notifications.discord_webhook_url
    if not webhook_url or not str(webhook_url).strip():
        debug("Discord Webhook desativado no config.yml. Pulando notificação remota.")
        return context.get("discord_message_id")

    payload = _build_embed_payload(status, context)
    message_id = context.get("discord_message_id")

    try:
        if message_id:
            response = requests.patch(f"{webhook_url}/messages/{message_id}", json=payload, timeout=5)
            response.raise_for_status()
            body = response.json() if hasattr(response, "json") else {}
            return body.get("id", message_id)

        response = requests.post(webhook_url, params={"wait": "true"}, json=payload, timeout=5)
        response.raise_for_status()
        body = response.json() if hasattr(response, "json") else {}
        return body.get("id")
    except Exception as exc:
        error(f"Falha ao enviar webhook do Discord: {exc}")
        return message_id
