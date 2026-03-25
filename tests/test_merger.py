import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.merger import mux_audio, validate_and_replace

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


@patch('src.merger.subprocess.Popen')
@patch('src.merger.get_allowed_streams')
def test_mux_audio_applies_itsoffset_only_to_audio_input(mock_get_allowed, mock_popen):
    mock_get_allowed.return_value = [2, 4]

    mock_process = MagicMock()
    mock_process.stdout = []
    mock_process.returncode = 0
    mock_popen.return_value = mock_process

    mux_audio(Path("movie_4k.mkv"), Path("audio_ptbr.ac3"), Path("output.mkv"), audio_offset_seconds=2.5)

    cmd = mock_popen.call_args.args[0]
    assert "-itsoffset" in cmd
    offset_index = cmd.index("-itsoffset")
    assert cmd[offset_index + 1] == "2.500"
    assert cmd[offset_index + 2] == "-i"

@patch('src.merger.subprocess.Popen')
@patch('src.merger.get_allowed_streams')
def test_mux_audio_optimize_only(mock_get_allowed, mock_popen):
    # Setup mocks
    mock_get_allowed.return_value = [1, 3]
    
    mock_process = MagicMock()
    mock_process.stdout = []
    mock_process.returncode = 0
    mock_popen.return_value = mock_process
    
    file_4k = Path("movie_4k.mkv")
    audio_ptbr = None
    output_tmp = Path("output.mkv")
    
    mux_audio(file_4k, audio_ptbr, output_tmp)
    
    # Assert
    mock_popen.assert_called_once()
    args, kwargs = mock_popen.call_args
    cmd = args[0]
    
    # Verify core mappings
    assert "-map" in cmd
    assert "0:v" in cmd
    assert "1:a" not in cmd
    
    # Verify dynamic mappings
    assert "0:1" in cmd
    assert "0:3" in cmd
    
    # Verify single input
    assert cmd.count("-i") == 1
    
    # Verify optimizations
    assert "-max_interleave_delta" in cmd
    assert "0" in cmd[cmd.index("-max_interleave_delta") + 1]
    
    # Verify no metadata for injected audio
    assert "language=por" not in cmd


@patch("src.merger.time.sleep", return_value=None)
@patch('src.merger.subprocess.Popen')
@patch('src.merger.get_allowed_streams')
def test_mux_audio_retries_transient_failure(mock_get_allowed, mock_popen, _mock_sleep, tmp_path: Path):
    mock_get_allowed.return_value = [1, 3]

    first_process = MagicMock()
    first_process.stdout = []
    first_process.returncode = 4294967283

    second_process = MagicMock()
    second_process.stdout = []
    second_process.returncode = 0

    mock_popen.side_effect = [first_process, second_process]

    output_tmp = tmp_path / "output.mkv"
    mux_audio(Path("movie_4k.mkv"), None, output_tmp)

    assert mock_popen.call_count == 2


@patch("src.merger.replace_original")
@patch("src.merger.validate_final_file")
def test_validate_and_replace_blocks_invalid_output(mock_validate_final_file, mock_replace_original):
    mock_validate_final_file.return_value = {"valid": False, "reason": "MISSING_PTBR"}

    with pytest.raises(ValueError):
        validate_and_replace(Path("output.mkv"), Path("movie_4k.mkv"))

    mock_replace_original.assert_not_called()


@patch("src.merger.replace_original")
@patch("src.merger.validate_final_file")
def test_validate_and_replace_replaces_original_when_validation_passes(mock_validate_final_file, mock_replace_original):
    mock_validate_final_file.return_value = {"valid": True, "reason": "OK"}

    result = validate_and_replace(Path("output.mkv"), Path("movie_4k.mkv"))

    assert result["valid"] is True
    mock_replace_original.assert_called_once_with(Path("output.mkv"), Path("movie_4k.mkv"))

