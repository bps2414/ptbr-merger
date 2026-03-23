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


@patch("src.analyzer.get_duration")
def test_diagnose_sync_marks_small_drift_as_offset_suspected(mock_get_duration):
    mock_get_duration.side_effect = [7200.0, 7245.0]

    diagnosis = diagnose_sync(
        Path("movie4k.mkv"),
        Path("movie1080p.mkv"),
        runtime_oficial=None,
    )

    assert diagnosis["category"] == "OFFSET_SUSPECTED"
    assert diagnosis["offset_estimate"] == pytest.approx(45.0, abs=0.001)


@patch("src.analyzer.get_duration")
@patch("src.analyzer.get_ptbr_stream_index")
def test_validate_final_file_requires_ptbr_and_duration_match(mock_stream_index, mock_get_duration):
    mock_stream_index.return_value = None
    mock_get_duration.side_effect = [7900.0, 7576.224]

    result = validate_final_file(Path("output_tmp.mkv"), Path("original.mkv"))

    assert result["valid"] is False
    assert result["reason"] == "MISSING_PTBR"
