import json
import re
import subprocess
from pathlib import Path
from typing import Optional

from src.config import get_config
from src.notifier import debug, error, info, warning

config = get_config()


def _probe_file(filepath: Path) -> dict:
    """
    Executa o ffprobe e retorna o JSON parseado com streams e format.
    """
    ffprobe_path = config.ffmpeg.ffprobe_path
    cmd = [
        str(ffprobe_path),
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_streams",
        "-show_format",
        str(filepath),
    ]

    try:
        debug(f"Executando ffprobe em: {filepath.name}")
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        if not result.stdout or result.stdout.strip() == "":
            error(f"O ffprobe retornou um stdout vazio para {filepath.name}")
            return {}
        return json.loads(result.stdout)
    except subprocess.CalledProcessError as exc:
        error(f"Erro executando ffprobe em {filepath.name}. STDERR: {exc.stderr}")
        return {}
    except json.JSONDecodeError as exc:
        error(f"Erro ao decodificar JSON do ffprobe para {filepath.name}: {exc}")
        return {}


def _is_ptbr_stream(tags: dict) -> bool:
    """
    Verifica se o idioma é PT-BR avaliando tanto tags.language quanto tags.title.
    """
    language = tags.get("language", "").lower()
    title = tags.get("title", "").lower()

    allowed_exact = {"por", "pt", "pt-br", "ptbr", "portuguese", "português"}

    if language in allowed_exact or title in allowed_exact:
        return True

    for tag in ["pt-br", "ptbr", "portuguese", "português"]:
        if tag in title:
            return True

    return bool(re.search(r"\b(pt|por)\b", title))


def get_ptbr_stream_index(filepath: Path) -> Optional[int]:
    """
    Procura uma faixa de áudio PT-BR sem assumir posição fixa.
    """
    probe = _probe_file(filepath)
    streams = probe.get("streams", [])

    for stream in streams:
        if stream.get("codec_type") != "audio":
            continue

        tags = stream.get("tags", {})
        if _is_ptbr_stream(tags):
            idx = stream.get("index")
            debug(f"Faixa PT-BR encontrada no índice {idx} em {filepath.name}")
            return idx

    debug(f"Nenhuma faixa PT-BR encontrada em {filepath.name}")
    return None


def get_allowed_streams(filepath: Path) -> list[int]:
    """
    Lista os índices de streams de áudio/legenda que devem ser preservados.
    """
    probe = _probe_file(filepath)
    streams = probe.get("streams", [])

    allowed_indices: list[int] = []
    allowed_langs_exact = {
        "por",
        "pt",
        "pt-br",
        "ptbr",
        "portuguese",
        "português",
        "eng",
        "en",
        "english",
        "jpn",
        "ja",
        "japanese",
        "und",
    }

    for stream in streams:
        codec_type = stream.get("codec_type")
        if codec_type not in ("audio", "subtitle"):
            continue

        tags = stream.get("tags", {})
        if not tags:
            allowed_indices.append(stream.get("index"))
            continue

        language = tags.get("language", "").lower()
        title = tags.get("title", "").lower()
        is_allowed = False

        if language == "" or language in allowed_langs_exact or title in allowed_langs_exact:
            is_allowed = True

        if not is_allowed:
            for tag in ["pt-br", "ptbr", "portuguese", "português", "english", "japanese"]:
                if tag in title:
                    is_allowed = True
                    break

        if not is_allowed and re.search(r"\b(pt|por|en|eng|ja|jpn|und)\b", title):
            is_allowed = True

        if is_allowed:
            allowed_indices.append(stream.get("index"))

    return allowed_indices


def has_ptbr_audio(filepath: Path) -> bool:
    return get_ptbr_stream_index(filepath) is not None


def get_duration(filepath: Path) -> float:
    probe = _probe_file(filepath)
    format_info = probe.get("format", {})
    duration_str = format_info.get("duration", "0")

    try:
        return float(duration_str)
    except ValueError:
        warning(f"Duração formatada ({duration_str}) inválida pelo ffprobe no arquivo {filepath.name}.")
        return 0.0


def _estimate_offset(duration_4k: float, duration_1080p: float) -> tuple[float | None, float]:
    if duration_4k <= 0.0 or duration_1080p <= 0.0:
        return None, 0.0
    return duration_1080p - duration_4k, 0.9


def diagnose_sync(file_4k: Path, file_1080p: Path, runtime_oficial: float | None = None) -> dict:
    """
    Gera um diagnóstico estruturado de compatibilidade entre o 4K e o 1080p.
    """
    max_diff = config.sync.max_duration_diff_seconds
    offset_threshold = getattr(config.diagnostics, "offset_suspected_threshold_seconds", 180)

    duration_4k = get_duration(file_4k)
    duration_1080p = get_duration(file_1080p)
    diagnosis = {
        "sync_ok": False,
        "category": "UNKNOWN_SYNC_FAILURE",
        "diff": 0.0,
        "runtime_4k": duration_4k,
        "runtime_1080p": duration_1080p,
        "runtime_oficial": runtime_oficial,
        "offset_estimate": None,
        "offset_confidence": 0.0,
    }

    if duration_4k == 0.0 or duration_1080p == 0.0:
        warning("Não foi possível validar sincronia (duração inválida ou nula).")
        return diagnosis

    diff = abs(duration_4k - duration_1080p)
    diagnosis["diff"] = diff

    offset_estimate, offset_confidence = _estimate_offset(duration_4k, duration_1080p)
    diagnosis["offset_estimate"] = offset_estimate
    diagnosis["offset_confidence"] = offset_confidence

    info(f"[Sincronia] 4K: {duration_4k:.3f}s | 1080p: {duration_1080p:.3f}s | Diferença exata: {diff:.3f}s")

    if diff <= max_diff:
        diagnosis["sync_ok"] = True
        diagnosis["category"] = "SYNC_OK"
        return diagnosis

    if runtime_oficial is not None and getattr(config.diagnostics, "enable_runtime_heuristics", True):
        diff_4k_official = abs(duration_4k - runtime_oficial)
        diff_1080p_official = abs(duration_1080p - runtime_oficial)

        if diff_4k_official <= max_diff and diff_1080p_official > max_diff:
            diagnosis["category"] = "CUT_MISMATCH"
            warning(
                f"Erro de sincronia: candidato 1080p diverge do runtime oficial em "
                f"{diff_1080p_official:.3f}s."
            )
            return diagnosis

        if diff_4k_official > max_diff and diff_1080p_official <= max_diff:
            diagnosis["category"] = "RUNTIME_INCOMPATIBLE"
            warning(
                f"Runtime 4K diverge do runtime oficial em {diff_4k_official:.3f}s; "
                "heurística marcou incompatibilidade estrutural."
            )
            return diagnosis

    if getattr(config.diagnostics, "enable_offset_diagnostics", True) and diff <= offset_threshold:
        diagnosis["category"] = "OFFSET_SUSPECTED"
        warning(
            f"Possível offset detectado: diferença de {diff:.3f}s dentro da janela "
            f"diagnóstica de {offset_threshold}s."
        )
        return diagnosis

    diagnosis["category"] = "CUT_MISMATCH"
    warning(f"Erro de sincronia: diferença de {diff:.3f}s excede o limite estipulado de {max_diff}s.")
    return diagnosis


def validate_final_file(output_file: Path, original_file: Path) -> dict:
    """
    Executa uma validação final antes da substituição destrutiva do original.
    """
    ptbr_stream_index = get_ptbr_stream_index(output_file)
    duration_output = get_duration(output_file)
    duration_original = get_duration(original_file)
    diff = abs(duration_output - duration_original)
    max_diff = config.sync.max_duration_diff_seconds

    if ptbr_stream_index is None:
        return {
            "valid": False,
            "reason": "MISSING_PTBR",
            "ptbr_stream_index": None,
            "duration_output": duration_output,
            "duration_original": duration_original,
            "diff": diff,
        }

    if duration_output == 0.0 or duration_original == 0.0:
        return {
            "valid": False,
            "reason": "INVALID_DURATION",
            "ptbr_stream_index": ptbr_stream_index,
            "duration_output": duration_output,
            "duration_original": duration_original,
            "diff": diff,
        }

    if diff > max_diff:
        return {
            "valid": False,
            "reason": "DURATION_MISMATCH",
            "ptbr_stream_index": ptbr_stream_index,
            "duration_output": duration_output,
            "duration_original": duration_original,
            "diff": diff,
        }

    return {
        "valid": True,
        "reason": "OK",
        "ptbr_stream_index": ptbr_stream_index,
        "duration_output": duration_output,
        "duration_original": duration_original,
        "diff": diff,
    }


def validate_sync(file_4k: Path, file_1080p: Path) -> bool:
    """
    Mantém compatibilidade com o fluxo antigo retornando apenas flag booleana.
    """
    return diagnose_sync(file_4k, file_1080p).get("sync_ok", False)
