from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from src.merger import mux_audio

@patch('src.merger.subprocess.Popen')
@patch('src.merger.get_allowed_streams')
def test_mux_audio_dynamic_mapping(mock_get_allowed, mock_popen):
    # Setup mocks
    mock_get_allowed.return_value = [2, 4]
    
    mock_process = MagicMock()
    mock_process.stdout = []
    mock_process.returncode = 0
    mock_popen.return_value = mock_process
    
    file_4k = Path("movie_4k.mkv")
    audio_ptbr = Path("audio_ptbr.ac3")
    output_tmp = Path("output.mkv")
    
    mux_audio(file_4k, audio_ptbr, output_tmp)
    
    # Assert
    mock_popen.assert_called_once()
    args, kwargs = mock_popen.call_args
    cmd = args[0]
    
    # Verify core mappings
    assert "-map" in cmd
    assert "0:v" in cmd
    assert "1:a" in cmd
    
    # Verify dynamic mappings
    assert "0:2" in cmd
    assert "0:4" in cmd
    
    # Verify removed old mappings
    assert "0:a" not in cmd
    assert "0:s?" not in cmd
    
    # Verify optimizations
    assert "-max_interleave_delta" in cmd
    assert "0" in cmd[cmd.index("-max_interleave_delta") + 1]
