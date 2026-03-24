import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.qbit_client import QbitAddResult
from src.queue_manager import QueueManager
from src.trigger import _resolve_manual_context, run_analyzer, run_merger


@patch("src.trigger.run_merger")
@patch("src.trigger.send_progress_update", return_value=None)
@patch("src.trigger._get_largest_mkv")
@patch("src.trigger.qbit_client.add_torrent")
@patch("src.trigger.radarr_client.find_best_ptbr_release")
@patch("src.trigger.analyzer.has_ptbr_audio", return_value=False)
def test_run_analyzer_processes_completed_duplicate_immediately(
    _mock_has_ptbr_audio,
    mock_find_best_release,
    mock_add_torrent,
    mock_get_largest_mkv,
    _mock_send_progress,
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

    args = mock_run_merger.call_args.args
    assert args[0] == matched_1080p
    assert args[1] == 0
    assert args[2] == "1368166"
    assert args[3]["title"] == "The Housemaid"
    assert args[3]["year"] == "2025"
    assert args[3]["infohash"] == "ff9b9024d88c50f30b03f76e16172a180a450daa"
    assert args[4] is False
    assert args[5] == "ff9b9024d88c50f30b03f76e16172a180a450daa"
    assert args[6] == [{"url": "https://tracker.example/torrent/123"}]
    assert args[7] == 0


@patch("src.trigger.qbit_client.remove_torrent")
@patch("src.trigger.radarr_client.apply_success_tag")
@patch("src.trigger.radarr_client.rescan_movie")
@patch("src.trigger.radarr_client.get_movie_by_tmdbid")
@patch("src.trigger.merger.validate_and_replace")
@patch("src.trigger.merger.mux_audio")
@patch("src.trigger.merger.extract_audio")
@patch("src.trigger.analyzer.get_ptbr_stream_index", return_value=2)
@patch("src.trigger.analyzer.diagnose_sync")
def test_run_merger_applies_success_tag_after_validation(
    mock_diagnose_sync,
    _mock_stream_index,
    mock_extract_audio,
    mock_mux_audio,
    mock_validate_and_replace,
    mock_get_movie,
    mock_rescan_movie,
    mock_apply_success_tag,
    mock_remove_torrent,
    tmp_path,
):
    import src.trigger as trigger

    trigger.queue_manager = QueueManager(tmp_path / "queue.json", max_attempts=3)
    file_4k = tmp_path / "movie4k.mkv"
    file_1080p = tmp_path / "movie1080p.mkv"
    file_4k.write_text("4k")
    file_1080p.write_text("1080p")

    mock_diagnose_sync.return_value = {
        "sync_ok": True,
        "category": "SYNC_OK",
        "diff": 0.0,
        "runtime_4k": 7200.0,
        "runtime_1080p": 7200.0,
        "runtime_oficial": 7200.0,
        "offset_estimate": 0.0,
        "offset_confidence": 1.0,
    }
    mock_get_movie.return_value = {
        "id": 42,
        "title": "The Housemaid",
        "year": 2025,
        "runtime": 120,
        "movieFile": {"path": str(file_4k)},
    }
    mock_validate_and_replace.return_value = {"valid": True, "reason": "OK"}

    run_merger(
        file_1080p,
        0,
        "1368166",
        {"title": "The Housemaid", "year": "2025"},
        False,
        "abc123hash",
        candidates=[],
        current_index=0,
    )

    mock_validate_and_replace.assert_called_once()
    mock_rescan_movie.assert_called_once_with(42)
    mock_apply_success_tag.assert_called_once_with(42)
    mock_remove_torrent.assert_called_once_with("abc123hash", delete_files=True)


@patch("src.trigger.notify_status")
@patch("src.trigger.analyzer.diagnose_sync")
@patch("src.trigger.radarr_client.get_movie_by_tmdbid")
def test_run_merger_marks_abandoned_after_repeated_failures(
    mock_get_movie,
    mock_diagnose_sync,
    mock_notify_status,
    tmp_path,
):
    import src.trigger as trigger

    trigger.queue_manager = QueueManager(tmp_path / "queue.json", max_attempts=2)
    file_4k = tmp_path / "movie4k.mkv"
    file_1080p = tmp_path / "movie1080p.mkv"
    file_4k.write_text("4k")
    file_1080p.write_text("1080p")

    mock_get_movie.return_value = {
        "id": 42,
        "title": "The Housemaid",
        "year": 2025,
        "runtime": 120,
        "movieFile": {"path": str(file_4k)},
    }
    mock_diagnose_sync.return_value = {
        "sync_ok": False,
        "category": "CUT_MISMATCH",
        "diff": 305.791,
        "runtime_4k": 7576.224,
        "runtime_1080p": 7882.015,
        "runtime_oficial": 7580.0,
        "offset_estimate": 305.791,
        "offset_confidence": 0.9,
    }

    run_merger(file_1080p, 0, "1368166", {"title": "The Housemaid", "year": "2025"}, False, "", candidates=[], current_index=0)
    run_merger(file_1080p, 0, "1368166", {"title": "The Housemaid", "year": "2025"}, False, "", candidates=[], current_index=0)

    assert trigger.queue_manager.get_entry("1368166")["status"] == "ABANDONED"
    assert any(call.args[0] == "ABANDONED" for call in mock_notify_status.call_args_list)


@patch("src.trigger.qbit_client.remove_torrent")
@patch("src.trigger.radarr_client.get_movie_by_tmdbid")
@patch("src.trigger.merger.validate_and_replace", side_effect=ValueError("validation failed"))
@patch("src.trigger.merger.mux_audio")
@patch("src.trigger.merger.extract_audio")
@patch("src.trigger.analyzer.get_ptbr_stream_index", return_value=2)
@patch("src.trigger.analyzer.diagnose_sync")
def test_run_merger_skips_qbit_cleanup_when_final_validation_fails(
    mock_diagnose_sync,
    _mock_stream_index,
    mock_extract_audio,
    mock_mux_audio,
    _mock_validate_and_replace,
    mock_get_movie,
    mock_remove_torrent,
    tmp_path,
):
    import src.trigger as trigger

    trigger.queue_manager = QueueManager(tmp_path / "queue.json", max_attempts=3)
    file_4k = tmp_path / "movie4k.mkv"
    file_1080p = tmp_path / "movie1080p.mkv"
    file_4k.write_text("4k")
    file_1080p.write_text("1080p")

    mock_diagnose_sync.return_value = {
        "sync_ok": True,
        "category": "SYNC_OK",
        "diff": 0.0,
        "runtime_4k": 7200.0,
        "runtime_1080p": 7200.0,
        "runtime_oficial": 7200.0,
        "offset_estimate": 0.0,
        "offset_confidence": 1.0,
    }
    mock_get_movie.return_value = {
        "id": 42,
        "title": "The Housemaid",
        "year": 2025,
        "runtime": 120,
        "movieFile": {"path": str(file_4k)},
    }

    with patch("src.trigger.notify_status") as mock_notify_status:
        try:
            run_merger(
                file_1080p,
                0,
                "1368166",
                {"title": "The Housemaid", "year": "2025"},
                False,
                "abc123hash",
                candidates=[],
                current_index=0,
            )
        except ValueError:
            pass

    mock_remove_torrent.assert_not_called()
    assert any(call.args[0] == "ERROR" for call in mock_notify_status.call_args_list)


@patch("src.trigger.qbit_client.add_torrent")
@patch("src.trigger.notify_status")
@patch("src.trigger.analyzer.diagnose_sync")
@patch("src.trigger.radarr_client.get_movie_by_tmdbid")
def test_run_merger_immediately_reprocesses_completed_duplicate_fallback(
    mock_get_movie,
    mock_diagnose_sync,
    mock_notify_status,
    mock_add_torrent,
    tmp_path,
):
    import src.trigger as trigger

    trigger.queue_manager = QueueManager(tmp_path / "queue.json", max_attempts=3)
    file_4k = tmp_path / "movie4k.mkv"
    file_1080p = tmp_path / "movie1080p.mkv"
    file_4k.write_text("4k")
    file_1080p.write_text("1080p")

    mock_get_movie.return_value = {
        "id": 49,
        "title": "Return to Silent Hill",
        "year": 2026,
        "runtime": 106,
        "movieFile": {"path": str(file_4k)},
    }
    mock_diagnose_sync.return_value = {
        "sync_ok": False,
        "category": "CUT_MISMATCH",
        "diff": 75.242,
        "runtime_4k": 6344.448,
        "runtime_1080p": 6419.690,
        "runtime_oficial": 6360.0,
        "offset_estimate": 75.242,
        "offset_confidence": 0.9,
    }
    mock_add_torrent.return_value = QbitAddResult(
        success=True,
        torrent_hash="cccccccccccccccccccccccccccccccccccccccc",
        content_path=str(file_1080p),
        save_path=str(tmp_path),
        state="stalledUP",
        existing=True,
        completed=True,
    )

    with patch("src.trigger.run_merger") as mock_recursive_run_merger:
        run_merger(
            file_1080p,
            0,
            "680493",
            {"title": "Return to Silent Hill", "year": "2026"},
            False,
            "aed99a85e83722d31ccb742a757c700923819619",
            candidates=[
                {"title": "candidate 1", "url": "https://tracker/1"},
                {"title": "candidate 2", "url": "https://tracker/2"},
            ],
            current_index=0,
        )

    mock_add_torrent.assert_called_once_with("https://tracker/2", "680493")
    recursive_args = mock_recursive_run_merger.call_args.args
    assert recursive_args[0] == file_1080p
    assert recursive_args[2] == "680493"
    assert recursive_args[7] == 1


@patch("src.trigger.qbit_client.add_torrent")
@patch("src.trigger.notify_status")
@patch("src.trigger.analyzer.diagnose_sync")
@patch("src.trigger.radarr_client.get_movie_by_tmdbid")
def test_run_merger_skips_fallback_candidates_with_duplicate_infohash(
    mock_get_movie,
    mock_diagnose_sync,
    mock_notify_status,
    mock_add_torrent,
    tmp_path,
):
    import src.trigger as trigger

    trigger.queue_manager = QueueManager(tmp_path / "queue.json", max_attempts=3)
    file_4k = tmp_path / "movie4k.mkv"
    file_1080p = tmp_path / "movie1080p.mkv"
    file_4k.write_text("4k")
    file_1080p.write_text("1080p")

    mock_get_movie.return_value = {
        "id": 49,
        "title": "Return to Silent Hill",
        "year": 2026,
        "runtime": 106,
        "movieFile": {"path": str(file_4k)},
    }
    mock_diagnose_sync.return_value = {
        "sync_ok": False,
        "category": "CUT_MISMATCH",
        "diff": 75.242,
        "runtime_4k": 6344.448,
        "runtime_1080p": 6419.690,
        "runtime_oficial": 6360.0,
        "offset_estimate": 75.242,
        "offset_confidence": 0.9,
    }
    mock_add_torrent.side_effect = [
        QbitAddResult(
            success=True,
            torrent_hash="aed99a85e83722d31ccb742a757c700923819619",
            content_path=str(file_1080p),
            save_path=str(tmp_path),
            state="stalledUP",
            existing=True,
            completed=True,
        ),
        QbitAddResult(
            success=True,
            torrent_hash="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            content_path=str(file_1080p),
            save_path=str(tmp_path),
            state="stalledUP",
            existing=True,
            completed=True,
        ),
    ]

    with patch("src.trigger.run_merger") as mock_recursive_run_merger:
        run_merger(
            file_1080p,
            0,
            "680493",
            {"title": "Return to Silent Hill", "year": "2026"},
            False,
            "aed99a85e83722d31ccb742a757c700923819619",
            candidates=[
                {"title": "candidate 1", "url": "https://tracker/1"},
                {"title": "candidate 2", "url": "https://tracker/2"},
                {"title": "candidate 3", "url": "https://tracker/3"},
            ],
            current_index=0,
        )

    assert mock_add_torrent.call_count == 2
    assert mock_add_torrent.call_args_list[0].args == ("https://tracker/2", "680493")
    assert mock_add_torrent.call_args_list[1].args == ("https://tracker/3", "680493")
    recursive_args = mock_recursive_run_merger.call_args.args
    assert recursive_args[5] == "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    assert recursive_args[7] == 2


@patch("src.trigger.radarr_client.get_movie_by_file_path")
def test_resolve_manual_context_uses_radarr_match_when_tmdb_is_missing(mock_get_movie_by_file_path):
    file_path = Path(r"D:\media\Alien: Romulus.mkv")
    mock_get_movie_by_file_path.return_value = {
        "tmdbId": 945961,
        "title": "Alien: Romulus",
        "year": 2024,
    }

    tmdb_id, title, year = _resolve_manual_context(file_path, "", "Desconhecido", "")

    assert tmdb_id == "945961"
    assert title == "Alien: Romulus"
    assert year == "2024"
