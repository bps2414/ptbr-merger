from pathlib import Path
from unittest.mock import patch
import pytest

from src.analyzer import get_allowed_streams

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
