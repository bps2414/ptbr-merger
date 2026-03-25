import os
import sys
from pathlib import Path
from unittest.mock import patch
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.analyzer import get_allowed_streams, diagnose_sync, validate_final_file

@pytest.fixture
def mock_probe():
    return {
        "streams": [
            {"index": 0, "codec_type": "video"},
            {"index": 1, "codec_type": "audio", "tags": {"language": "eng", "title": "English"}},
            {"index": 2, "codec_type": "audio", "tags": {"language": "fre", "title": "French"}},
            {"index": 3, "codec_type": "audio", "tags": {"language": "por", "title": "Portuguese"}},
            {"index": 4, "codec_type": "subtitle", "tags": {"language": "ger"}},
            {"index": 5, "codec_type": "subtitle", "tags": {"language": "und"}},
            {"index": 6, "codec_type": "subtitle"},
            {"index": 7, "codec_type": "audio", "tags": {"title": "Brazillian Portuguese"}},
            {"index": 8, "codec_type": "audio", "tags": {"language": "jpn"}},
        ]
    }

@patch('src.analyzer._probe_file')
def test_get_allowed_streams(mock_probe_file, mock_probe):
    mock_probe_file.return_value = mock_probe
    filepath = Path("dummy.mkv")
    
    # Expected behavior:
    # 0: video (ignored, handled separately by merger)
    # 1: eng (allowed)
    # 2: fre (disallowed)
    # 3: por (allowed)
    # 4: ger (disallowed)
    # 5: und (allowed)
    # 6: missing tag (allowed)
    # 7: Brazillian Portuguese title (allowed)
    # 8: jpn (allowed)
    
    allowed = get_allowed_streams(filepath)
    
    assert allowed == [1, 3, 5, 6, 7, 8]


@patch("src.analyzer.get_duration")
def test_diagnose_sync_detects_cut_mismatch_when_diff_is_large(mock_get_duration):
    mock_get_duration.side_effect = [7576.224, 7882.015]

    diagnosis = diagnose_sync(
        Path("movie4k.mkv"),
        Path("movie1080p.mkv"),
        runtime_oficial=7580.0,
    )

    assert diagnosis["category"] == "CUT_MISMATCH"
    assert diagnosis["sync_ok"] is False
    assert diagnosis["diff"] == pytest.approx(305.791, abs=0.001)


@patch("src.analyzer.config")
@patch("src.analyzer.get_duration")
def test_diagnose_sync_marks_small_drift_as_offset_suspected(mock_get_duration, mock_config):
    mock_get_duration.side_effect = [7200.0, 7245.0]
    mock_config.sync.max_duration_diff_seconds = 30
    mock_config.diagnostics.offset_suspected_threshold_seconds = 180
    mock_config.diagnostics.enable_runtime_heuristics = True
    mock_config.diagnostics.enable_offset_diagnostics = True
    mock_config.diagnostics.enable_auto_offset = False
    mock_config.diagnostics.auto_offset_max_seconds = 90
    mock_config.diagnostics.auto_offset_min_confidence = 0.85
    mock_config.fingerprint.enabled = False

    diagnosis = diagnose_sync(
        Path("movie4k.mkv"),
        Path("movie1080p.mkv"),
        runtime_oficial=None,
    )

    assert diagnosis["category"] == "OFFSET_SUSPECTED"
    assert diagnosis["offset_estimate"] == pytest.approx(45.0, abs=0.001)
    assert diagnosis["auto_offset_eligible"] is False
    assert diagnosis["fingerprint_recommended"] is False


@patch("src.analyzer.get_duration")
@patch("src.analyzer.config")
def test_diagnose_sync_marks_offset_as_auto_offset_eligible(mock_config, mock_get_duration):
    mock_get_duration.side_effect = [7200.0, 7245.0]
    mock_config.sync.max_duration_diff_seconds = 30
    mock_config.diagnostics.offset_suspected_threshold_seconds = 180
    mock_config.diagnostics.enable_runtime_heuristics = True
    mock_config.diagnostics.enable_offset_diagnostics = True
    mock_config.diagnostics.enable_auto_offset = True
    mock_config.diagnostics.auto_offset_max_seconds = 90
    mock_config.diagnostics.auto_offset_min_confidence = 0.85
    mock_config.fingerprint.enabled = True

    diagnosis = diagnose_sync(
        Path("movie4k.mkv"),
        Path("movie1080p.mkv"),
        runtime_oficial=None,
    )

    assert diagnosis["category"] == "OFFSET_SUSPECTED"
    assert diagnosis["auto_offset_eligible"] is True
    assert diagnosis["auto_offset_reason"] == "eligible"
    assert diagnosis["fingerprint_recommended"] is True


@patch("src.analyzer.get_duration")
@patch("src.analyzer.get_ptbr_stream_index")
def test_validate_final_file_requires_ptbr_and_duration_match(mock_stream_index, mock_get_duration):
    mock_stream_index.return_value = None
    mock_get_duration.side_effect = [7900.0, 7576.224]

    result = validate_final_file(Path("output_tmp.mkv"), Path("original.mkv"))

    assert result["valid"] is False
    assert result["reason"] == "MISSING_PTBR"
