import os
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.qbit_client import QbitAddResult
from src.trigger import run_analyzer


@patch("src.trigger.run_merger")
@patch("src.trigger._get_largest_mkv")
@patch("src.trigger.qbit_client.add_torrent")
@patch("src.trigger.radarr_client.find_best_ptbr_release")
@patch("src.trigger.analyzer.has_ptbr_audio", return_value=False)
def test_run_analyzer_processes_completed_duplicate_immediately(
    _mock_has_ptbr_audio,
    mock_find_best_release,
    mock_add_torrent,
    mock_get_largest_mkv,
    mock_run_merger,
):
    movie_file = Path(r"D:\media\movie4k.mkv")
    matched_1080p = Path(r"D:\Filmes\A.Empregada.2025.1080p.WEB-DL.DUAL.5.1\A.Empregada.2025.1080p.WEB-DL.DUAL.5.1.mkv")

    mock_find_best_release.return_value = [{"url": "https://tracker.example/torrent/123"}]
    mock_add_torrent.return_value = QbitAddResult(
        success=True,
        torrent_hash="ff9b9024d88c50f30b03f76e16172a180a450daa",
        content_path=str(matched_1080p.parent),
        save_path=r"D:\Filmes",
        state="uploading",
        existing=True,
        completed=True,
    )
    mock_get_largest_mkv.return_value = matched_1080p

    run_analyzer(movie_file, "1368166", "The Housemaid", "2025", False, "")

    mock_run_merger.assert_called_once_with(
        matched_1080p,
        0,
        "1368166",
        {"title": "The Housemaid", "year": "2025"},
        False,
        "ff9b9024d88c50f30b03f76e16172a180a450daa",
        [{"url": "https://tracker.example/torrent/123"}],
        0,
    )
