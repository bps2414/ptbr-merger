import os
import sys
from pathlib import Path
from unittest.mock import patch

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.audio_fingerprint import _classify_measurements, measure_offset_at_position


def test_classify_measurements_returns_offset_ok_for_consistent_offsets():
    result = _classify_measurements(
        [
            {"position": "head", "measured_offset": -8.2, "confidence": 0.91},
            {"position": "mid", "measured_offset": -8.0, "confidence": 0.88},
            {"position": "tail", "measured_offset": -8.1, "confidence": 0.90},
        ],
        sync_threshold_seconds=30,
        min_confidence=0.7,
        consistency_tolerance_seconds=0.75,
    )

    assert result["category"] == "FINGERPRINT_OFFSET_OK"
    assert result["confidence"] >= 0.7


def test_classify_measurements_returns_sync_ok_for_near_zero_offset():
    result = _classify_measurements(
        [
            {"position": "head", "measured_offset": 0.1, "confidence": 0.91},
            {"position": "mid", "measured_offset": -0.2, "confidence": 0.88},
            {"position": "tail", "measured_offset": 0.15, "confidence": 0.90},
        ],
        sync_threshold_seconds=30,
        min_confidence=0.7,
        consistency_tolerance_seconds=0.75,
    )

    assert result["category"] == "FINGERPRINT_SYNC_OK"


def test_classify_measurements_returns_drift_for_inconsistent_offsets():
    result = _classify_measurements(
        [
            {"position": "head", "measured_offset": -2.0, "confidence": 0.9},
            {"position": "mid", "measured_offset": 4.2, "confidence": 0.9},
            {"position": "tail", "measured_offset": 11.4, "confidence": 0.9},
        ],
        sync_threshold_seconds=3,
        min_confidence=0.7,
        consistency_tolerance_seconds=0.75,
    )

    assert result["category"] == "FINGERPRINT_DRIFT_SUSPECTED"


def test_classify_measurements_returns_low_confidence():
    result = _classify_measurements(
        [{"position": "head", "measured_offset": -8.0, "confidence": 0.2}],
        sync_threshold_seconds=3,
        min_confidence=0.7,
        consistency_tolerance_seconds=0.75,
    )

    assert result["category"] == "FINGERPRINT_LOW_CONFIDENCE"


@patch("src.audio_fingerprint._extract_pcm_samples")
def test_measure_offset_at_position_returns_signed_offset(mock_extract_pcm_samples):
    sample_rate = 8
    window = np.array([0, 1, 0, -1, 0, 1, 0, -1], dtype=np.float32)
    search = np.concatenate(
        [
            np.zeros(sample_rate * 2, dtype=np.float32),
            window,
            np.zeros(sample_rate, dtype=np.float32),
        ]
    )
    mock_extract_pcm_samples.side_effect = [window, search]

    result = measure_offset_at_position(
        file_4k=Path("movie4k.mkv"),
        file_1080p=Path("movie1080p.mkv"),
        position="head",
        duration_4k=1.0,
        sample_rate=sample_rate,
        window_seconds=1.0,
        max_offset_seconds=2.0,
    )

    assert result is not None
    assert result["measured_offset"] < 0
