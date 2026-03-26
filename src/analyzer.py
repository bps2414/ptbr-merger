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
    Verifica se o idioma e PT-BR avaliando tanto tags.language quanto tags.title.
    """
    language = tags.get("language", "").lower()
    title = tags.get("title", "").lower()

    allowed_exact = {"por", "pt", "pt-br", "ptbr", "portuguese", "portugues"}

    if language in allowed_exact or title in allowed_exact:
        return True

    for tag in ["pt-br", "ptbr", "portuguese", "portugues"]:
        if tag in title:
            return True

    return bool(re.search(r"\b(pt|por)\b", title))


def get_ptbr_stream_index(filepath: Path) -> Optional[int]:
    """
    Procura uma faixa de audio PT-BR sem assumir posicao fixa.
    """
    probe = _probe_file(filepath)
    streams = probe.get("streams", [])

    for stream in streams:
        if stream.get("codec_type") != "audio":
            continue

        tags = stream.get("tags", {})
        if _is_ptbr_stream(tags):
            idx = stream.get("index")
            debug(f"Faixa PT-BR encontrada no indice {idx} em {filepath.name}")
            return idx

    debug(f"Nenhuma faixa PT-BR encontrada em {filepath.name}")
    return None


def get_allowed_streams(filepath: Path) -> list[int]:
    """
    Lista os indices de streams de audio/legenda que devem ser preservados.
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
        "portugues",
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
            for tag in ["pt-br", "ptbr", "portuguese", "portugues", "english", "japanese"]:
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
        warning(f"Duracao formatada ({duration_str}) invalida pelo ffprobe no arquivo {filepath.name}.")
        return 0.0


def _estimate_offset(duration_4k: float, duration_1080p: float) -> tuple[float | None, float]:
    if duration_4k <= 0.0 or duration_1080p <= 0.0:
        return None, 0.0
    return duration_1080p - duration_4k, 0.9


def _mark_sync_ok(diagnosis: dict) -> dict:
    diagnosis.update(
        {
            "sync_ok": True,
            "category": "SYNC_OK",
            "recoverability": "not-needed",
            "terminal": False,
            "preserve_candidate": False,
            "recovery_reason": "sync-ok",
            "auto_offset_reason": "sync-ok",
            "fingerprint_reason": "sync-ok",
        }
    )
    return diagnosis


def _mark_terminal(diagnosis: dict, *, category: str, auto_offset_reason: str, fingerprint_reason: str, recovery_reason: str) -> dict:
    diagnosis.update(
        {
            "sync_ok": False,
            "category": category,
            "recoverability": "terminal",
            "terminal": True,
            "preserve_candidate": False,
            "recovery_reason": recovery_reason,
            "auto_offset_eligible": False,
            "auto_offset_reason": auto_offset_reason,
            "fingerprint_recommended": False,
            "fingerprint_reason": fingerprint_reason,
        }
    )
    return diagnosis


def _mark_recoverable(
    diagnosis: dict,
    *,
    category: str,
    recoverability: str,
    recovery_reason: str,
    fingerprint_reason: str,
    fingerprint_recommended: bool = True,
) -> dict:
    diagnosis.update(
        {
            "sync_ok": False,
            "category": category,
            "recoverability": recoverability,
            "terminal": False,
            "preserve_candidate": True,
            "recovery_reason": recovery_reason,
            "fingerprint_recommended": fingerprint_recommended,
            "fingerprint_reason": fingerprint_reason,
        }
    )
    return diagnosis


def diagnose_sync(file_4k: Path, file_1080p: Path, runtime_oficial: float | None = None) -> dict:
    """
    Gera um diagnostico estruturado de compatibilidade entre o 4K e o 1080p.
    """
    max_diff = config.sync.max_duration_diff_seconds
    offset_threshold = float(getattr(config.diagnostics, "offset_suspected_threshold_seconds", 180))
    recoverable_edge_threshold = float(getattr(config.diagnostics, "recoverable_edge_diff_seconds", offset_threshold))
    ambiguous_threshold = max(
        recoverable_edge_threshold,
        float(getattr(config.diagnostics, "ambiguous_recoverable_diff_seconds", 240)),
    )

    duration_4k = get_duration(file_4k)
    duration_1080p = get_duration(file_1080p)
    diagnosis = {
        "sync_ok": False,
        "category": "UNKNOWN_SYNC_FAILURE",
        "recoverability": "unknown",
        "terminal": True,
        "preserve_candidate": False,
        "recovery_reason": "not-evaluated",
        "diff": 0.0,
        "runtime_4k": duration_4k,
        "runtime_1080p": duration_1080p,
        "runtime_oficial": runtime_oficial,
        "offset_estimate": None,
        "offset_confidence": 0.0,
        "auto_offset_eligible": False,
        "auto_offset_reason": "not-evaluated",
        "fingerprint_recommended": False,
        "fingerprint_reason": "not-evaluated",
    }

    if duration_4k == 0.0 or duration_1080p == 0.0:
        warning("Nao foi possivel validar sincronia (duracao invalida ou nula).")
        return diagnosis

    diff = abs(duration_4k - duration_1080p)
    diagnosis["diff"] = diff

    offset_estimate, offset_confidence = _estimate_offset(duration_4k, duration_1080p)
    diagnosis["offset_estimate"] = offset_estimate
    diagnosis["offset_confidence"] = offset_confidence

    info(f"[Sincronia] 4K: {duration_4k:.3f}s | 1080p: {duration_1080p:.3f}s | Diferenca exata: {diff:.3f}s")

    if diff <= max_diff:
        return _mark_sync_ok(diagnosis)

    if runtime_oficial is not None and getattr(config.diagnostics, "enable_runtime_heuristics", True):
        diff_4k_official = abs(duration_4k - runtime_oficial)
        diff_1080p_official = abs(duration_1080p - runtime_oficial)

        if diff_4k_official <= max_diff and diff_1080p_official > max_diff:
            if diff_1080p_official <= recoverable_edge_threshold:
                warning(
                    f"Divergencia de runtime do candidato em {diff_1080p_official:.3f}s; "
                    "tratando como diferenca potencial de intro/outro."
                )
                return _mark_recoverable(
                    diagnosis,
                    category="INTRO_OUTRO_DIVERGENCE",
                    recoverability="recoverable",
                    recovery_reason="runtime-edge-divergence",
                    fingerprint_reason="intro-outro-divergence",
                )
            warning(
                f"Erro de sincronia: candidato 1080p diverge do runtime oficial em "
                f"{diff_1080p_official:.3f}s."
            )
            return _mark_terminal(
                diagnosis,
                category="CUT_MISMATCH",
                auto_offset_reason="runtime-shows-cut-mismatch",
                fingerprint_reason="runtime-cut-mismatch",
                recovery_reason="runtime-cut-mismatch",
            )

        if diff_4k_official > max_diff and diff_1080p_official <= max_diff:
            warning(
                f"Runtime 4K diverge do runtime oficial em {diff_4k_official:.3f}s; "
                "heuristica marcou incompatibilidade estrutural."
            )
            return _mark_terminal(
                diagnosis,
                category="RUNTIME_INCOMPATIBLE",
                auto_offset_reason="runtime-incompatible",
                fingerprint_reason="runtime-incompatible",
                recovery_reason="runtime-incompatible",
            )

    if getattr(config.diagnostics, "enable_offset_diagnostics", True) and diff <= offset_threshold:
        _mark_recoverable(
            diagnosis,
            category="OFFSET_SUSPECTED",
            recoverability="recoverable",
            recovery_reason="offset-suspected",
            fingerprint_reason="offset-suspected",
        )
        max_auto_offset = getattr(config.diagnostics, "auto_offset_max_seconds", offset_threshold)
        min_confidence = getattr(config.diagnostics, "auto_offset_min_confidence", 0.85)
        if not getattr(config.diagnostics, "enable_auto_offset", False):
            diagnosis["auto_offset_reason"] = "auto-offset-disabled"
        elif diagnosis["offset_estimate"] is None:
            diagnosis["auto_offset_reason"] = "missing-offset"
        elif abs(float(diagnosis["offset_estimate"])) > max_auto_offset:
            diagnosis["auto_offset_reason"] = "offset-too-large"
        elif float(diagnosis["offset_confidence"]) < float(min_confidence):
            diagnosis["auto_offset_reason"] = "low-confidence"
        else:
            diagnosis["auto_offset_eligible"] = True
            diagnosis["auto_offset_reason"] = "eligible"
        warning(
            f"Possivel offset detectado: diferenca de {diff:.3f}s dentro da janela "
            f"diagnostica de {offset_threshold}s."
        )
        return diagnosis

    if diff <= recoverable_edge_threshold:
        warning(
            f"Diferenca grande ({diff:.3f}s), mas ainda dentro da janela de divergencia de borda "
            f"({recoverable_edge_threshold}s). Preservando candidato para recuperacao."
        )
        return _mark_recoverable(
            diagnosis,
            category="INTRO_OUTRO_DIVERGENCE",
            recoverability="recoverable",
            recovery_reason="edge-divergence-window",
            fingerprint_reason="edge-divergence-window",
        )

    if diff <= ambiguous_threshold:
        warning(
            f"Diferenca grande ({diff:.3f}s) em faixa ambigua ate {ambiguous_threshold}s; "
            "preservando candidato para investigacao adicional."
        )
        return _mark_recoverable(
            diagnosis,
            category="AMBIGUOUS_RECOVERABLE",
            recoverability="ambiguous",
            recovery_reason="large-diff-ambiguous",
            fingerprint_reason="large-diff-ambiguous",
        )

    warning(f"Erro de sincronia: diferenca de {diff:.3f}s excede o limite estipulado de {max_diff}s.")
    return _mark_terminal(
        diagnosis,
        category="CUT_MISMATCH",
        auto_offset_reason="diff-too-large",
        fingerprint_reason="diff-too-large",
        recovery_reason="diff-too-large",
    )


def validate_final_file(output_file: Path, original_file: Path) -> dict:
    """
    Executa uma validacao final antes da substituicao destrutiva do original.
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


def validate_recovery_attempt(
    output_file: Path,
    original_file: Path,
    *,
    diagnosis: dict,
    strategy: str | None,
    source_audio_file: Path | None = None,
    recovered_audio_file: Path | None = None,
    audio_offset_seconds: float | None = None,
    fingerprint_category: str | None = None,
    trim_start_seconds: float = 0.0,
    trim_end_seconds: float = 0.0,
) -> dict:
    """
    Valida recovery automatico com checks conservadores e especificos por estrategia.
    """
    validation = validate_final_file(output_file, original_file)
    strict_max_diff = min(
        float(getattr(config.recovery, "post_validation_max_diff_seconds", config.sync.max_duration_diff_seconds)),
        float(config.sync.max_duration_diff_seconds),
    )
    result = {
        **validation,
        "strategy": strategy,
        "strict_max_diff": strict_max_diff,
        "postcheck_reason": "not-run",
    }

    if not validation.get("valid"):
        result["postcheck_reason"] = "final-validation-failed"
        return result

    if float(validation.get("diff") or 0.0) > strict_max_diff:
        result.update(
            {
                "valid": False,
                "reason": "RECOVERY_FINAL_DIFF_TOO_LARGE",
                "postcheck_reason": "final-diff-too-large",
            }
        )
        return result

    if strategy == "offset":
        applied_offset = None if audio_offset_seconds is None else float(audio_offset_seconds)
        if applied_offset is None:
            result.update(
                {
                    "valid": False,
                    "reason": "RECOVERY_OFFSET_MISSING",
                    "postcheck_reason": "offset-missing",
                }
            )
            return result

        if abs(applied_offset) > float(getattr(config.recovery, "max_offset_seconds", 90)):
            result.update(
                {
                    "valid": False,
                    "reason": "RECOVERY_OFFSET_TOO_LARGE",
                    "postcheck_reason": "offset-too-large",
                }
            )
            return result

        if not (diagnosis.get("auto_offset_eligible") or fingerprint_category == "FINGERPRINT_OFFSET_OK"):
            result.update(
                {
                    "valid": False,
                    "reason": "RECOVERY_OFFSET_EVIDENCE_MISSING",
                    "postcheck_reason": "offset-evidence-missing",
                }
            )
            return result

        expected_offset = diagnosis.get("offset_estimate")
        tolerance = max(0.5, strict_max_diff)
        if (
            expected_offset is not None
            and fingerprint_category != "FINGERPRINT_OFFSET_OK"
            and abs(abs(applied_offset) - abs(float(expected_offset))) > tolerance
        ):
            result.update(
                {
                    "valid": False,
                    "reason": "RECOVERY_OFFSET_UNEXPECTED",
                    "postcheck_reason": "offset-unexpected",
                }
            )
            return result

        result.update(
            {
                "valid": True,
                "reason": "RECOVERY_OFFSET_OK",
                "postcheck_reason": "offset-confirmed",
            }
        )
        return result

    if strategy == "edge-trim":
        if source_audio_file is None or recovered_audio_file is None:
            result.update(
                {
                    "valid": False,
                    "reason": "RECOVERY_TRIM_AUDIO_MISSING",
                    "postcheck_reason": "trim-audio-missing",
                }
            )
            return result

        source_duration = float(get_duration(source_audio_file) or 0.0)
        recovered_duration = float(get_duration(recovered_audio_file) or 0.0)
        trimmed_total = max(0.0, source_duration - recovered_duration)
        expected_trim = float(trim_start_seconds or 0.0) + float(trim_end_seconds or 0.0)
        if expected_trim <= 0.0:
            expected_trim = max(0.0, float(diagnosis.get("diff") or 0.0))
        trim_tolerance = float(getattr(config.recovery, "trim_tolerance_seconds", 1.5))
        runtime_gap = abs(recovered_duration - float(validation.get("duration_original") or 0.0))
        result.update(
            {
                "source_audio_duration": source_duration,
                "recovered_audio_duration": recovered_duration,
                "trimmed_total": trimmed_total,
                "expected_trim": expected_trim,
                "runtime_gap": runtime_gap,
            }
        )

        if source_duration == 0.0 or recovered_duration == 0.0:
            result.update(
                {
                    "valid": False,
                    "reason": "RECOVERY_TRIM_INVALID_DURATION",
                    "postcheck_reason": "trim-invalid-duration",
                }
            )
            return result

        if trimmed_total < float(getattr(config.recovery, "min_trim_seconds", 0.0)):
            result.update(
                {
                    "valid": False,
                    "reason": "RECOVERY_TRIM_TOO_SMALL",
                    "postcheck_reason": "trim-too-small",
                }
            )
            return result

        if abs(trimmed_total - expected_trim) > trim_tolerance:
            result.update(
                {
                    "valid": False,
                    "reason": "RECOVERY_TRIM_AMOUNT_MISMATCH",
                    "postcheck_reason": "trim-amount-mismatch",
                }
            )
            return result

        if runtime_gap > strict_max_diff:
            result.update(
                {
                    "valid": False,
                    "reason": "RECOVERY_TRIM_RUNTIME_MISMATCH",
                    "postcheck_reason": "trim-runtime-mismatch",
                }
            )
            return result

        result.update(
            {
                "valid": True,
                "reason": "RECOVERY_EDGE_TRIM_OK",
                "postcheck_reason": "trim-aligned",
            }
        )
        return result

    result.update(
        {
            "valid": False,
            "reason": "RECOVERY_STRATEGY_UNSUPPORTED",
            "postcheck_reason": "strategy-unsupported",
        }
    )
    return result


def validate_sync(file_4k: Path, file_1080p: Path) -> bool:
    """
    Mantem compatibilidade com o fluxo antigo retornando apenas flag booleana.
    """
    return diagnose_sync(file_4k, file_1080p).get("sync_ok", False)
