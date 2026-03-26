import math
import subprocess
from pathlib import Path

import numpy as np

from src.config import get_config
from src.notifier import debug, warning

config = get_config()

_FINGERPRINT_SUCCESS = {"FINGERPRINT_SYNC_OK", "FINGERPRINT_OFFSET_OK"}
_FINGERPRINT_FAILURE = {"FINGERPRINT_DRIFT_SUSPECTED", "FINGERPRINT_CUT_MISMATCH", "FINGERPRINT_LOW_CONFIDENCE"}


def _position_to_ratio(position: str) -> float:
    mapping = {
        "head": 0.15,
        "mid": 0.50,
        "tail": 0.80,
    }
    return mapping.get(str(position).strip().lower(), 0.50)


def _normalize_samples(samples: np.ndarray) -> np.ndarray:
    if samples.size == 0:
        return np.array([], dtype=np.float32)
    normalized = samples.astype(np.float32)
    normalized -= float(np.mean(normalized))
    std = float(np.std(normalized))
    if std <= 1e-6:
        return np.array([], dtype=np.float32)
    normalized /= std
    return normalized


def _extract_pcm_samples(file_path: Path, start_seconds: float, duration_seconds: float, sample_rate: int) -> np.ndarray:
    ffmpeg_path = config.ffmpeg.ffmpeg_path
    cmd = [
        str(ffmpeg_path),
        "-v",
        "error",
        "-ss",
        f"{max(0.0, float(start_seconds)):.3f}",
        "-i",
        str(file_path),
        "-t",
        f"{max(0.0, float(duration_seconds)):.3f}",
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-f",
        "s16le",
        "-acodec",
        "pcm_s16le",
        "-",
    ]

    result = subprocess.run(cmd, capture_output=True, check=True)
    if not result.stdout:
        return np.array([], dtype=np.float32)
    return np.frombuffer(result.stdout, dtype=np.int16).astype(np.float32)


def _fft_correlate_valid(search: np.ndarray, window: np.ndarray) -> np.ndarray:
    if search.size < window.size or window.size == 0:
        return np.array([], dtype=np.float32)
    n = int(2 ** math.ceil(math.log2(search.size + window.size - 1)))
    search_fft = np.fft.rfft(search, n=n)
    window_fft = np.fft.rfft(window[::-1], n=n)
    corr = np.fft.irfft(search_fft * window_fft, n=n)
    valid = corr[window.size - 1 : search.size]
    return valid.astype(np.float32)


def measure_offset_at_position(
    *,
    file_4k: Path,
    file_1080p: Path,
    position: str,
    duration_4k: float,
    sample_rate: int,
    window_seconds: float,
    max_offset_seconds: float,
) -> dict | None:
    ratio = _position_to_ratio(position)
    window_start_4k = max(0.0, (duration_4k * ratio) - (window_seconds / 2.0))
    search_start_1080p = max(0.0, window_start_4k - max_offset_seconds)
    search_duration_1080p = window_seconds + (2.0 * max_offset_seconds)

    try:
        window_4k = _normalize_samples(_extract_pcm_samples(file_4k, window_start_4k, window_seconds, sample_rate))
        search_1080p = _normalize_samples(_extract_pcm_samples(file_1080p, search_start_1080p, search_duration_1080p, sample_rate))
    except subprocess.CalledProcessError as exc:
        warning(f"Falha extraindo PCM para fingerprint na posição {position}: {exc}")
        return None

    if window_4k.size == 0 or search_1080p.size == 0 or search_1080p.size < window_4k.size:
        return None

    correlation = _fft_correlate_valid(search_1080p, window_4k)
    if correlation.size == 0:
        return None

    best_index = int(np.argmax(np.abs(correlation)))
    best_value = float(correlation[best_index]) / float(window_4k.size)
    match_time_1080p = search_start_1080p + (best_index / sample_rate)
    measured_offset = window_start_4k - match_time_1080p

    debug(
        f"Fingerprint {position}: janela_4k={window_start_4k:.3f}s "
        f"match_1080p={match_time_1080p:.3f}s offset={measured_offset:.3f}s score={abs(best_value):.3f}"
    )
    return {
        "position": position,
        "window_start_4k": window_start_4k,
        "match_time_1080p": match_time_1080p,
        "measured_offset": measured_offset,
        "confidence": abs(best_value),
    }


def _classify_measurements(
    measurements: list[dict],
    *,
    sync_threshold_seconds: float,
    min_confidence: float,
    consistency_tolerance_seconds: float,
) -> dict:
    result = {
        "category": "FINGERPRINT_LOW_CONFIDENCE",
        "best_offset_seconds": None,
        "confidence": 0.0,
        "measurements": measurements,
    }
    if not measurements:
        return result

    offsets = np.array([float(item["measured_offset"]) for item in measurements], dtype=np.float32)
    confidences = np.array([float(item["confidence"]) for item in measurements], dtype=np.float32)
    best_offset = float(np.median(offsets))
    confidence = float(np.mean(confidences))
    spread = float(np.max(np.abs(offsets - best_offset))) if offsets.size > 1 else 0.0

    result.update(
        {
            "best_offset_seconds": best_offset,
            "confidence": confidence,
            "spread_seconds": spread,
            "positions_used": [item["position"] for item in measurements],
        }
    )

    if confidence < float(min_confidence):
        return result

    if spread > float(consistency_tolerance_seconds):
        result["category"] = "FINGERPRINT_DRIFT_SUSPECTED"
        return result

    if abs(best_offset) <= float(consistency_tolerance_seconds):
        result["category"] = "FINGERPRINT_SYNC_OK"
        return result

    result["category"] = "FINGERPRINT_OFFSET_OK"
    return result


def fingerprint_sync(
    *,
    file_4k: Path,
    file_1080p: Path,
    duration_4k: float,
    positions: list[str] | None = None,
) -> dict:
    fingerprint_cfg = config.fingerprint
    selected_positions = list(positions or getattr(fingerprint_cfg, "positions", ["head", "mid", "tail"]))
    measurements = []

    for position in selected_positions:
        measurement = measure_offset_at_position(
            file_4k=file_4k,
            file_1080p=file_1080p,
            position=position,
            duration_4k=duration_4k,
            sample_rate=int(getattr(fingerprint_cfg, "sample_rate", 2000)),
            window_seconds=float(getattr(fingerprint_cfg, "window_seconds", 12)),
            max_offset_seconds=float(getattr(fingerprint_cfg, "max_offset_seconds", 90)),
        )
        if measurement:
            measurements.append(measurement)

    result = _classify_measurements(
        measurements,
        sync_threshold_seconds=float(getattr(config.sync, "max_duration_diff_seconds", 30)),
        min_confidence=float(getattr(fingerprint_cfg, "min_confidence", 0.7)),
        consistency_tolerance_seconds=float(getattr(fingerprint_cfg, "consistency_tolerance_seconds", 0.75)),
    )

    return result
