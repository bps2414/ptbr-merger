from datetime import datetime, timedelta, timezone
import os
import sys
from argparse import Namespace
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.history_manager import HistoryManager
from src.qbit_client import QbitAddResult
from src.queue_manager import QueueManager
from src.retry_queue_manager import RetryQueueManager
from src.sync_intelligence import GroupHistoryManager
from src.trigger import _resolve_manual_context, parse_args, run_analyzer, run_merger


@pytest.fixture(autouse=True)
def isolate_trigger_state(tmp_path):
    import src.trigger as trigger

    original_queue_manager = trigger.queue_manager
    original_history_manager = trigger.history_manager
    original_group_history_manager = trigger.group_history_manager
    original_retry_queue_manager = getattr(trigger, "retry_queue_manager", None)

    trigger.queue_manager = QueueManager(tmp_path / "queue.json", max_attempts=3)
    trigger.history_manager = HistoryManager(tmp_path / "history.json", max_entries=500)
    trigger.group_history_manager = GroupHistoryManager(tmp_path / "group_history.json")
    trigger.retry_queue_manager = RetryQueueManager(tmp_path / "retry_queue.json")

    yield

    trigger.queue_manager = original_queue_manager
    trigger.history_manager = original_history_manager
    trigger.group_history_manager = original_group_history_manager
    trigger.retry_queue_manager = original_retry_queue_manager


@patch("src.trigger.run_merger")
@patch("src.trigger.send_progress_update", return_value=None)
@patch("src.trigger._get_largest_mkv")
@patch("src.trigger.qbit_client.add_torrent")
@patch("src.trigger.radarr_client.find_best_ptbr_release")
@patch("src.trigger.radarr_client.get_movie_by_tmdbid", return_value=None)
@patch("src.trigger.analyzer.has_ptbr_audio", return_value=False)
def test_run_analyzer_processes_completed_duplicate_immediately(
    _mock_has_ptbr_audio,
    _mock_get_movie_by_tmdbid,
    mock_find_best_release,
    mock_add_torrent,
    mock_get_largest_mkv,
    _mock_send_progress,
    mock_run_merger,
):
    movie_file = Path(r"D:\media\movie4k.mkv")
    matched_1080p = Path(r"D:\Filmes\A.Empregada.2025.1080p.WEB-DL.DUAL.5.1\A.Empregada.2025.1080p.WEB-DL.DUAL.5.1.mkv")

    mock_find_best_release.return_value = [{"url": "https://tracker.example/torrent/123", "infohash": "knownhash123"}]
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
    assert args[6] == [{"url": "https://tracker.example/torrent/123", "infohash": "knownhash123"}]
    assert args[7] == 0
    assert mock_add_torrent.call_args.args == ("https://tracker.example/torrent/123", "1368166")
    assert mock_add_torrent.call_args.kwargs == {"known_infohash": "knownhash123"}


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


@patch("src.trigger.qbit_client.remove_torrent")
@patch("src.trigger.radarr_client.apply_success_tag")
@patch("src.trigger.radarr_client.rescan_movie")
@patch("src.trigger.radarr_client.get_movie_by_tmdbid")
@patch("src.trigger.audio_fingerprint.fingerprint_sync")
@patch("src.trigger.analyzer.validate_recovery_attempt")
@patch("src.trigger.merger.validate_and_replace")
@patch("src.trigger.merger.mux_audio")
@patch("src.trigger.merger.extract_audio")
@patch("src.trigger.analyzer.get_ptbr_stream_index", return_value=2)
@patch("src.trigger.analyzer.diagnose_sync")
def test_run_merger_applies_auto_offset_when_diagnosis_marks_it_eligible(
    mock_diagnose_sync,
    _mock_stream_index,
    _mock_extract_audio,
    mock_mux_audio,
    mock_validate_and_replace,
    mock_validate_recovery,
    mock_fingerprint_sync,
    mock_get_movie,
    mock_rescan_movie,
    mock_apply_success_tag,
    mock_remove_torrent,
    tmp_path,
):
    import src.trigger as trigger

    trigger.queue_manager = QueueManager(tmp_path / "queue.json", max_attempts=3)
    trigger.group_history_manager = GroupHistoryManager(tmp_path / "group_history.json")
    trigger.config.fingerprint.enabled = True
    file_4k = tmp_path / "movie4k.mkv"
    file_1080p = tmp_path / "movie1080p.mkv"
    file_4k.write_text("4k")
    file_1080p.write_text("1080p")

    mock_diagnose_sync.return_value = {
        "sync_ok": False,
        "category": "OFFSET_SUSPECTED",
        "diff": 12.5,
        "runtime_4k": 7200.0,
        "runtime_1080p": 7212.5,
        "runtime_oficial": 7201.0,
        "offset_estimate": 12.5,
        "offset_confidence": 0.95,
        "auto_offset_eligible": False,
        "auto_offset_reason": "auto-offset-disabled",
        "fingerprint_recommended": True,
        "fingerprint_reason": "offset-suspected",
    }
    mock_fingerprint_sync.return_value = {
        "category": "FINGERPRINT_OFFSET_OK",
        "best_offset_seconds": -12.5,
        "confidence": 0.92,
        "positions_used": ["head", "mid", "tail"],
    }
    mock_get_movie.return_value = {
        "id": 42,
        "title": "The Housemaid",
        "year": 2025,
        "runtime": 120,
        "movieFile": {"path": str(file_4k)},
    }
    mock_validate_recovery.return_value = {"valid": True, "reason": "RECOVERY_OFFSET_OK", "postcheck_reason": "offset-confirmed"}
    mock_validate_and_replace.return_value = {"valid": True, "reason": "OK"}

    run_merger(
        file_1080p,
        0,
        "1368166",
        {"title": "The Housemaid", "year": "2025", "group": "sf", "source_1080p": "AMZN.WEBDL"},
        False,
        "abc123hash",
        candidates=[],
        current_index=0,
    )

    assert mock_mux_audio.call_args.kwargs["audio_offset_seconds"] == -12.5
    assert trigger.group_history_manager.summarize()["recent_attempts"][-1]["result"] == "FINGERPRINT_OFFSET_OK"
    mock_apply_success_tag.assert_called_once_with(42)
    mock_remove_torrent.assert_called_once_with("abc123hash", delete_files=True)
    trigger.config.fingerprint.enabled = False


@patch("src.trigger.qbit_client.remove_torrent")
@patch("src.trigger.radarr_client.apply_success_tag")
@patch("src.trigger.radarr_client.rescan_movie")
@patch("src.trigger.radarr_client.get_movie_by_tmdbid")
@patch("src.trigger.analyzer.validate_recovery_attempt")
@patch("src.trigger.merger.validate_and_replace")
@patch("src.trigger.merger.mux_audio")
@patch("src.trigger.merger.trim_audio_edges")
@patch("src.trigger.merger.extract_audio")
@patch("src.trigger.analyzer.get_ptbr_stream_index", return_value=2)
@patch("src.trigger.analyzer.diagnose_sync")
def test_run_merger_attempts_edge_trim_recovery_for_intro_outro_divergence(
    mock_diagnose_sync,
    _mock_stream_index,
    _mock_extract_audio,
    mock_trim_audio,
    mock_mux_audio,
    mock_validate_and_replace,
    mock_validate_recovery,
    mock_get_movie,
    mock_rescan_movie,
    mock_apply_success_tag,
    mock_remove_torrent,
    tmp_path,
):
    import src.trigger as trigger

    trigger.queue_manager = QueueManager(tmp_path / "queue.json", max_attempts=3)
    trigger.group_history_manager = GroupHistoryManager(tmp_path / "group_history.json")
    trigger.config.recovery.enabled = True
    file_4k = tmp_path / "movie4k.mkv"
    file_1080p = tmp_path / "movie1080p.mkv"
    file_4k.write_text("4k")
    file_1080p.write_text("1080p")

    mock_diagnose_sync.return_value = {
        "sync_ok": False,
        "category": "INTRO_OUTRO_DIVERGENCE",
        "recoverability": "recoverable",
        "terminal": False,
        "preserve_candidate": True,
        "recovery_reason": "edge-padding",
        "diff": 24.0,
        "runtime_4k": 7200.0,
        "runtime_1080p": 7224.0,
        "runtime_oficial": 7200.0,
        "offset_estimate": 24.0,
        "offset_confidence": 0.9,
        "auto_offset_eligible": False,
        "auto_offset_reason": "edge-first",
        "fingerprint_recommended": False,
        "fingerprint_reason": "intro-outro-divergence",
    }
    mock_get_movie.return_value = {
        "id": 42,
        "title": "The Housemaid",
        "year": 2025,
        "runtime": 120,
        "movieFile": {"path": str(file_4k)},
    }
    mock_validate_recovery.return_value = {"valid": True, "reason": "RECOVERY_EDGE_TRIM_OK", "postcheck_reason": "trim-aligned"}
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

    assert mock_trim_audio.call_args.kwargs["trim_start_seconds"] == 0.0
    assert mock_trim_audio.call_args.kwargs["trim_end_seconds"] == 24.0
    assert mock_mux_audio.call_args.args[1].name == "audio_ptbr_recovery.eac3"
    assert mock_mux_audio.call_args.kwargs["audio_offset_seconds"] is None
    assert trigger.queue_manager.get_entry("1368166")["status"] == "SUCCESS"
    mock_apply_success_tag.assert_called_once_with(42)
    mock_remove_torrent.assert_called_once_with("abc123hash", delete_files=True)
    trigger.config.recovery.enabled = True


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
@patch("src.trigger.radarr_client.get_movie_by_tmdbid")
@patch("src.trigger.audio_fingerprint.fingerprint_sync")
@patch("src.trigger.analyzer.validate_recovery_attempt")
@patch("src.trigger.merger.validate_and_replace", side_effect=ValueError("validation failed"))
@patch("src.trigger.merger.mux_audio")
@patch("src.trigger.merger.extract_audio")
@patch("src.trigger.analyzer.get_ptbr_stream_index", return_value=2)
@patch("src.trigger.analyzer.diagnose_sync")
def test_run_merger_falls_back_when_auto_offset_validation_fails(
    mock_diagnose_sync,
    _mock_stream_index,
    _mock_extract_audio,
    _mock_mux_audio,
    _mock_validate_and_replace,
    mock_validate_recovery,
    mock_fingerprint_sync,
    mock_get_movie,
    mock_notify_status,
    mock_add_torrent,
    tmp_path,
):
    import src.trigger as trigger

    trigger.queue_manager = QueueManager(tmp_path / "queue.json", max_attempts=3)
    trigger.group_history_manager = GroupHistoryManager(tmp_path / "group_history.json")
    trigger.config.fingerprint.enabled = True
    file_4k = tmp_path / "movie4k.mkv"
    file_1080p = tmp_path / "movie1080p.mkv"
    file_4k.write_text("4k")
    file_1080p.write_text("1080p")

    mock_get_movie.return_value = {
        "id": 49,
        "title": "Alien: Romulus",
        "year": 2024,
        "runtime": 119,
        "movieFile": {"path": str(file_4k)},
    }
    mock_diagnose_sync.return_value = {
        "sync_ok": False,
        "category": "OFFSET_SUSPECTED",
        "diff": 8.4,
        "runtime_4k": 7140.0,
        "runtime_1080p": 7148.4,
        "runtime_oficial": 7141.0,
        "offset_estimate": 8.4,
        "offset_confidence": 0.95,
        "auto_offset_eligible": False,
        "auto_offset_reason": "auto-offset-disabled",
        "fingerprint_recommended": True,
        "fingerprint_reason": "offset-suspected",
    }
    mock_fingerprint_sync.return_value = {
        "category": "FINGERPRINT_OFFSET_OK",
        "best_offset_seconds": -8.4,
        "confidence": 0.91,
        "positions_used": ["head", "mid"],
    }
    mock_validate_recovery.return_value = {"valid": True, "reason": "RECOVERY_OFFSET_OK", "postcheck_reason": "offset-confirmed"}
    mock_add_torrent.return_value = QbitAddResult(success=True, torrent_hash="next-hash")

    run_merger(
        file_1080p,
        0,
        "945961",
        {"title": "Alien: Romulus", "year": "2024", "group": "sf", "source_1080p": "AMZN.WEBDL"},
        False,
        "curr-hash",
        candidates=[
            {"title": "candidate 1", "url": "https://tracker/1", "group": "sf", "source_1080p": "AMZN.WEBDL"},
            {"title": "candidate 2", "url": "https://tracker/2", "group": "byndr", "source_1080p": "AMZN.WEBDL"},
        ],
        current_index=0,
    )

    assert any(call.args[0] == "OFFSET_SUSPECTED_FAILED" for call in mock_notify_status.call_args_list)
    assert mock_add_torrent.call_args.args == ("https://tracker/2", "945961")
    assert mock_add_torrent.call_args.kwargs == {"known_infohash": None}
    assert trigger.group_history_manager.summarize()["recent_attempts"][-1]["result"] == "OFFSET_SUSPECTED_FAILED"
    trigger.config.fingerprint.enabled = False


@patch("src.trigger.qbit_client.add_torrent")
@patch("src.trigger.notify_status")
@patch("src.trigger.radarr_client.get_movie_by_tmdbid")
@patch("src.trigger.analyzer.validate_recovery_attempt")
@patch("src.trigger.merger.validate_and_replace")
@patch("src.trigger.merger.mux_audio")
@patch("src.trigger.merger.trim_audio_edges")
@patch("src.trigger.merger.extract_audio")
@patch("src.trigger.analyzer.get_ptbr_stream_index", return_value=2)
@patch("src.trigger.analyzer.diagnose_sync")
def test_run_merger_falls_back_when_edge_trim_postcheck_fails(
    mock_diagnose_sync,
    _mock_stream_index,
    _mock_extract_audio,
    _mock_trim_audio,
    _mock_mux_audio,
    mock_validate_and_replace,
    mock_validate_recovery,
    mock_get_movie,
    mock_notify_status,
    mock_add_torrent,
    tmp_path,
):
    import src.trigger as trigger

    trigger.queue_manager = QueueManager(tmp_path / "queue.json", max_attempts=3)
    trigger.group_history_manager = GroupHistoryManager(tmp_path / "group_history.json")
    trigger.config.recovery.enabled = True
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
        "category": "INTRO_OUTRO_DIVERGENCE",
        "recoverability": "recoverable",
        "terminal": False,
        "preserve_candidate": True,
        "recovery_reason": "edge-padding",
        "diff": 24.0,
        "runtime_4k": 7200.0,
        "runtime_1080p": 7224.0,
        "runtime_oficial": 7200.0,
        "offset_estimate": 24.0,
        "offset_confidence": 0.9,
        "auto_offset_eligible": False,
        "auto_offset_reason": "edge-first",
        "fingerprint_recommended": False,
        "fingerprint_reason": "intro-outro-divergence",
    }
    mock_validate_recovery.return_value = {
        "valid": False,
        "reason": "RECOVERY_TRIM_AMOUNT_MISMATCH",
        "postcheck_reason": "trim-amount-mismatch",
    }
    mock_add_torrent.return_value = QbitAddResult(success=True, torrent_hash="next-hash")

    run_merger(
        file_1080p,
        0,
        "1368166",
        {"title": "The Housemaid", "year": "2025"},
        False,
        "curr-hash",
        candidates=[
            {"title": "candidate 1", "url": "https://tracker/1"},
            {"title": "candidate 2", "url": "https://tracker/2"},
        ],
        current_index=0,
    )

    assert any(call.args[0] == "AUTO_RECOVERY_FAILED" for call in mock_notify_status.call_args_list)
    assert mock_add_torrent.call_args.args == ("https://tracker/2", "1368166")
    assert mock_validate_and_replace.call_count == 0
    assert trigger.group_history_manager.summarize()["recent_attempts"][-1]["result"] == "AUTO_RECOVERY_FAILED"


@patch("src.trigger.notify_status")
@patch("src.trigger.radarr_client.get_movie_by_tmdbid")
@patch("src.trigger.audio_fingerprint.fingerprint_sync")
@patch("src.trigger.analyzer.diagnose_sync")
def test_run_merger_blocks_offset_when_fingerprint_confirms_cut_mismatch(
    mock_diagnose_sync,
    mock_fingerprint_sync,
    mock_get_movie,
    mock_notify_status,
    tmp_path,
):
    import src.trigger as trigger

    trigger.queue_manager = QueueManager(tmp_path / "queue.json", max_attempts=3)
    trigger.group_history_manager = GroupHistoryManager(tmp_path / "group_history.json")
    trigger.config.fingerprint.enabled = True
    file_4k = tmp_path / "movie4k.mkv"
    file_1080p = tmp_path / "movie1080p.mkv"
    file_4k.write_text("4k")
    file_1080p.write_text("1080p")

    mock_get_movie.return_value = {
        "id": 49,
        "title": "Sonic the Hedgehog 3",
        "year": 2024,
        "runtime": 110,
        "movieFile": {"path": str(file_4k)},
    }
    mock_diagnose_sync.return_value = {
        "sync_ok": False,
        "category": "OFFSET_SUSPECTED",
        "diff": 21.0,
        "runtime_4k": 6600.0,
        "runtime_1080p": 6621.0,
        "runtime_oficial": 6600.0,
        "offset_estimate": 21.0,
        "offset_confidence": 0.95,
        "auto_offset_eligible": False,
        "auto_offset_reason": "auto-offset-disabled",
        "fingerprint_recommended": True,
        "fingerprint_reason": "offset-suspected",
    }
    mock_fingerprint_sync.return_value = {
        "category": "FINGERPRINT_CUT_MISMATCH",
        "best_offset_seconds": None,
        "confidence": 0.88,
        "positions_used": ["head", "mid", "tail"],
    }

    run_merger(file_1080p, 0, "939243", {"title": "Sonic the Hedgehog 3", "year": "2024"}, False, "", candidates=[], current_index=0)

    assert any(call.args[0] == "FINGERPRINT_CUT_MISMATCH" for call in mock_notify_status.call_args_list)
    assert trigger.group_history_manager.summarize()["recent_attempts"][-1]["result"] == "FINGERPRINT_CUT_MISMATCH"
    trigger.config.fingerprint.enabled = False


@patch("src.trigger.qbit_client.remove_torrent")
@patch("src.trigger.qbit_client.add_torrent")
@patch("src.trigger.notify_status")
@patch("src.trigger.analyzer.diagnose_sync")
@patch("src.trigger.radarr_client.get_movie_by_tmdbid")
def test_run_merger_immediately_reprocesses_completed_duplicate_fallback(
    mock_get_movie,
    mock_diagnose_sync,
    mock_notify_status,
    mock_add_torrent,
    mock_remove_torrent,
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

    mock_add_torrent.assert_called_once_with("https://tracker/2", "680493", known_infohash=None)
    mock_remove_torrent.assert_called_once_with("aed99a85e83722d31ccb742a757c700923819619", delete_files=True)
    recursive_args = mock_recursive_run_merger.call_args.args
    assert recursive_args[0] == file_1080p
    assert recursive_args[2] == "680493"
    assert recursive_args[7] == 1


@patch("src.trigger.qbit_client.add_torrent")
@patch("src.trigger.notify_status")
@patch("src.trigger.analyzer.diagnose_sync")
@patch("src.trigger.radarr_client.get_movie_by_tmdbid")
def test_run_merger_preserves_recoverable_candidate_without_triggering_fallback(
    mock_get_movie,
    mock_diagnose_sync,
    mock_notify_status,
    mock_add_torrent,
    tmp_path,
):
    import src.trigger as trigger

    trigger.queue_manager = QueueManager(tmp_path / "queue.json", max_attempts=3)
    trigger.group_history_manager = GroupHistoryManager(tmp_path / "group_history.json")
    trigger.config.recovery.enabled = True
    trigger.config.recovery.allow_ambiguous = False
    file_4k = tmp_path / "movie4k.mkv"
    file_1080p = tmp_path / "movie1080p.mkv"
    file_4k.write_text("4k")
    file_1080p.write_text("1080p")

    mock_get_movie.return_value = {
        "id": 49,
        "title": "Sonic the Hedgehog 3",
        "year": 2024,
        "runtime": 110,
        "movieFile": {"path": str(file_4k)},
    }
    mock_diagnose_sync.return_value = {
        "sync_ok": False,
        "category": "AMBIGUOUS_RECOVERABLE",
        "recoverability": "ambiguous",
        "terminal": False,
        "preserve_candidate": True,
        "recovery_reason": "fingerprint-inconclusive",
        "diff": 141.179,
        "runtime_4k": 6605.349,
        "runtime_1080p": 6746.528,
        "runtime_oficial": 6600.0,
        "offset_estimate": 141.179,
        "offset_confidence": 0.9,
        "auto_offset_eligible": False,
        "auto_offset_reason": "await-phase-3",
        "fingerprint_recommended": False,
        "fingerprint_reason": "fingerprint-inconclusive",
    }

    run_merger(
        file_1080p,
        0,
        "939243",
        {"title": "Sonic the Hedgehog 3", "year": "2024"},
        False,
        "aeecdea6debe2f7ffa20c904769d4ef0059cbfe7",
        candidates=[
            {"title": "candidate 1", "url": "https://tracker/1"},
            {"title": "candidate 2", "url": "https://tracker/2"},
        ],
        current_index=0,
    )

    queue_entry = trigger.queue_manager.get_entry("939243")
    assert queue_entry["status"] == "PENDING"
    assert queue_entry["phase"] == "recoverability"
    assert queue_entry["diagnosis_category"] == "AMBIGUOUS_RECOVERABLE"
    assert trigger.group_history_manager.summarize()["recent_attempts"][-1]["result"] == "AMBIGUOUS_RECOVERABLE"
    mock_notify_status.assert_called_once()
    assert mock_notify_status.call_args.args[0] == "AMBIGUOUS_RECOVERABLE"
    mock_add_torrent.assert_not_called()
    trigger.config.recovery.allow_ambiguous = False


@patch("src.trigger.qbit_client.remove_torrent")
@patch("src.trigger.radarr_client.apply_success_tag")
@patch("src.trigger.radarr_client.rescan_movie")
@patch("src.trigger.radarr_client.get_movie_by_tmdbid")
@patch("src.trigger.audio_fingerprint.fingerprint_sync")
@patch("src.trigger.analyzer.validate_recovery_attempt")
@patch("src.trigger.merger.validate_and_replace")
@patch("src.trigger.merger.mux_audio")
@patch("src.trigger.merger.trim_audio_edges")
@patch("src.trigger.merger.extract_audio")
@patch("src.trigger.analyzer.get_ptbr_stream_index", return_value=2)
@patch("src.trigger.analyzer.diagnose_sync")
def test_run_merger_attempts_edge_trim_when_fingerprint_is_inconclusive_for_intro_outro(
    mock_diagnose_sync,
    _mock_stream_index,
    _mock_extract_audio,
    mock_trim_audio,
    mock_mux_audio,
    mock_validate_and_replace,
    mock_validate_recovery,
    mock_fingerprint_sync,
    mock_get_movie,
    mock_rescan_movie,
    mock_apply_success_tag,
    mock_remove_torrent,
    tmp_path,
):
    import src.trigger as trigger

    trigger.queue_manager = QueueManager(tmp_path / "queue.json", max_attempts=3)
    trigger.group_history_manager = GroupHistoryManager(tmp_path / "group_history.json")
    trigger.config.fingerprint.enabled = True
    trigger.config.recovery.enabled = True
    file_4k = tmp_path / "movie4k.mkv"
    file_1080p = tmp_path / "movie1080p.mkv"
    file_4k.write_text("4k")
    file_1080p.write_text("1080p")

    mock_get_movie.return_value = {
        "id": 49,
        "title": "Sonic the Hedgehog 3",
        "year": 2024,
        "runtime": 110,
        "movieFile": {"path": str(file_4k)},
    }
    mock_diagnose_sync.return_value = {
        "sync_ok": False,
        "category": "INTRO_OUTRO_DIVERGENCE",
        "recoverability": "recoverable",
        "terminal": False,
        "preserve_candidate": True,
        "recovery_reason": "edge-padding",
        "diff": 141.179,
        "runtime_4k": 6605.349,
        "runtime_1080p": 6746.528,
        "runtime_oficial": 6600.0,
        "offset_estimate": 141.179,
        "offset_confidence": 0.9,
        "auto_offset_eligible": False,
        "auto_offset_reason": "await-phase-3",
        "fingerprint_recommended": True,
        "fingerprint_reason": "edge-padding",
    }
    mock_fingerprint_sync.return_value = {
        "category": "FINGERPRINT_LOW_CONFIDENCE",
        "best_offset_seconds": None,
        "confidence": 0.41,
        "positions_used": ["head", "mid"],
    }
    mock_validate_recovery.return_value = {"valid": True, "reason": "RECOVERY_EDGE_TRIM_OK", "postcheck_reason": "trim-aligned"}
    mock_validate_and_replace.return_value = {"valid": True, "reason": "OK"}

    run_merger(
        file_1080p,
        0,
        "939243",
        {"title": "Sonic the Hedgehog 3", "year": "2024"},
        False,
        "aeecdea6debe2f7ffa20c904769d4ef0059cbfe7",
        candidates=[
            {"title": "candidate 1", "url": "https://tracker/1"},
            {"title": "candidate 2", "url": "https://tracker/2"},
        ],
        current_index=0,
    )

    queue_entry = trigger.queue_manager.get_entry("939243")
    assert queue_entry["status"] == "SUCCESS"
    assert mock_trim_audio.call_args.kwargs["trim_end_seconds"] == 141.179
    assert mock_mux_audio.call_args.args[1].name == "audio_ptbr_recovery.eac3"
    assert trigger.group_history_manager.summarize()["recent_attempts"][-1]["result"] == "SUCCESS"
    mock_rescan_movie.assert_called_once_with(49)
    mock_apply_success_tag.assert_called_once_with(49)
    mock_remove_torrent.assert_called_once_with("aeecdea6debe2f7ffa20c904769d4ef0059cbfe7", delete_files=True)
    trigger.config.fingerprint.enabled = False


@patch("src.trigger.qbit_client.remove_torrent")
@patch("src.trigger.notify_status")
@patch("src.trigger.analyzer.diagnose_sync")
@patch("src.trigger.radarr_client.get_movie_by_tmdbid")
def test_run_merger_removes_failed_torrent_when_no_fallback_candidates_remain(
    mock_get_movie,
    mock_diagnose_sync,
    mock_notify_status,
    mock_remove_torrent,
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
        "title": "Sonic the Hedgehog 3",
        "year": 2024,
        "runtime": 110,
        "movieFile": {"path": str(file_4k)},
    }
    mock_diagnose_sync.return_value = {
        "sync_ok": False,
        "category": "CUT_MISMATCH",
        "recoverability": "terminal",
        "terminal": True,
        "preserve_candidate": False,
        "recovery_reason": "structural-cut-mismatch",
        "diff": 141.179,
        "runtime_4k": 6605.349,
        "runtime_1080p": 6746.528,
        "runtime_oficial": 6600.0,
        "offset_estimate": 141.179,
        "offset_confidence": 0.9,
    }

    run_merger(
        file_1080p,
        0,
        "939243",
        {"title": "Sonic the Hedgehog 3", "year": "2024"},
        False,
        "aeecdea6debe2f7ffa20c904769d4ef0059cbfe7",
        candidates=[
            {"title": "candidate 1", "url": "https://tracker/1"},
        ],
        current_index=0,
    )

    mock_remove_torrent.assert_called_once_with("aeecdea6debe2f7ffa20c904769d4ef0059cbfe7", delete_files=True)
    assert any(call.args[0] == "CUT_MISMATCH" for call in mock_notify_status.call_args_list)


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
    assert mock_add_torrent.call_args_list[0].kwargs == {"known_infohash": None}
    assert mock_add_torrent.call_args_list[1].args == ("https://tracker/3", "680493")
    assert mock_add_torrent.call_args_list[1].kwargs == {"known_infohash": None}
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


def test_parse_args_accepts_manual_recovery_flags():
    with patch.object(
        sys,
        "argv",
        [
            "trigger.py",
            "--manual-recovery",
            "--tmdb-id",
            "939243",
            "--qbit-path",
            r"D:\downloads\Sonic.3.1080p",
            "--candidate-index",
            "2",
            "--force-offset-seconds",
            "-8.4",
            "--trim-start-seconds",
            "1.5",
            "--trim-end-seconds",
            "24",
            "--reuse-last-recovery",
            "--preserve-recovery-artifacts",
        ],
    ):
        args = parse_args()

    assert args.manual_recovery is True
    assert args.tmdb_id == "939243"
    assert args.candidate_index == 2
    assert args.force_offset_seconds == -8.4
    assert args.trim_start_seconds == 1.5
    assert args.trim_end_seconds == 24.0
    assert args.reuse_last_recovery is True
    assert args.preserve_recovery_artifacts is True


@patch("src.trigger.run_merger")
@patch("src.trigger.radarr_client.find_best_ptbr_release")
@patch("src.trigger.radarr_client.get_movie_by_tmdbid")
@patch("src.trigger._resolve_qbit_completed_file")
@patch("src.trigger.parse_args")
def test_main_routes_manual_recovery_to_run_merger(
    mock_parse_args,
    mock_resolve_qbit_completed_file,
    mock_get_movie,
    mock_find_best_release,
    mock_run_merger,
    tmp_path,
):
    import src.trigger as trigger

    source_file = tmp_path / "candidate1080p.mkv"
    source_file.write_text("1080p")

    mock_parse_args.return_value = Namespace(
        dry_run=False,
        file_path=None,
        qbit_path=str(source_file),
        qbit_category=None,
        qbit_tags=None,
        qbit_hash="hash123",
        retry_pending=False,
        manual_recovery=True,
        tmdb_id="939243",
        candidate_index=2,
        force_offset_seconds=-8.4,
        trim_start_seconds=0.0,
        trim_end_seconds=24.0,
        reuse_last_recovery=False,
        preserve_recovery_artifacts=True,
    )
    mock_resolve_qbit_completed_file.return_value = source_file
    mock_get_movie.return_value = {"title": "Sonic the Hedgehog 3", "year": 2024}
    mock_find_best_release.return_value = [
        {"title": "candidate 1"},
        {"title": "candidate 2"},
        {"title": "candidate 3"},
    ]

    trigger.main()

    _, kwargs = mock_run_merger.call_args
    manual_request = kwargs["manual_request"]
    assert manual_request["manual_recovery"] is True
    assert manual_request["manual_candidate_index"] == 2
    assert manual_request["manual_force_offset_seconds"] == -8.4
    assert manual_request["manual_trim_end_seconds"] == 24.0
    assert manual_request["manual_source_path"] == str(source_file)


@patch("src.trigger.notify_status")
@patch("src.trigger.send_progress_update", return_value="discord-progress")
@patch("src.trigger._optimize_in_place")
@patch("src.trigger.radarr_client.get_movie_by_tmdbid", return_value=None)
@patch("src.trigger.analyzer.has_ptbr_audio", return_value=True)
def test_run_analyzer_persists_terminal_skipped_has_ptbr_state(
    _mock_has_ptbr_audio,
    _mock_get_movie_by_tmdbid,
    mock_optimize_in_place,
    _mock_send_progress,
    mock_notify_status,
    tmp_path,
):
    import src.trigger as trigger

    trigger.queue_manager = QueueManager(tmp_path / "queue.json", max_attempts=3)
    trigger.history_manager = HistoryManager(tmp_path / "history.json", max_entries=500)
    trigger.group_history_manager = GroupHistoryManager(tmp_path / "group_history.json")

    def _notify(status, context):
        assert status == "SKIPPED_HAS_PTBR"
        context["discord_message_id"] = "discord-final"

    mock_notify_status.side_effect = _notify

    movie_file = tmp_path / "movie4k.mkv"
    movie_file.write_text("4k")

    run_analyzer(movie_file, "1084242", "Zootopia 2", "2025", False, "")

    entry = trigger.queue_manager.get_entry("1084242")
    assert entry["status"] == "SUCCESS"
    assert entry["phase"] == "analyzer"
    assert entry["discord_message_id"] == "discord-final"
    mock_optimize_in_place.assert_called_once()


@patch("src.trigger.notify_status")
@patch("src.trigger._optimize_in_place")
@patch("src.trigger.bazarr_client.lookup_ptbr_subtitles", return_value={"configured": False, "available": False, "reason": "disabled"})
@patch("src.trigger.radarr_client.get_last_release_search_summary", return_value={"reason": "NO_AVAILABLE_SEEDS"})
@patch("src.trigger.radarr_client.find_best_ptbr_release", return_value=[])
@patch("src.trigger.analyzer.has_ptbr_audio", return_value=False)
def test_run_analyzer_schedules_retry_for_no_available_seeds(
    _mock_has_ptbr_audio,
    _mock_find_best_release,
    _mock_summary,
    mock_bazarr_lookup,
    mock_optimize,
    mock_notify_status,
    tmp_path,
):
    import src.trigger as trigger

    trigger.queue_manager = QueueManager(tmp_path / "queue.json", max_attempts=3)
    trigger.history_manager = HistoryManager(tmp_path / "history.json", max_entries=500)
    trigger.group_history_manager = GroupHistoryManager(tmp_path / "group_history.json")
    trigger.retry_queue_manager = RetryQueueManager(tmp_path / "retry_queue.json")

    movie_file = tmp_path / "movie4k.mkv"
    movie_file.write_text("4k")

    run_analyzer(movie_file, "1084242", "Zootopia 2", "2025", False, "")

    retry_entry = trigger.retry_queue_manager.get_entry("1084242")
    assert retry_entry["reason"] == "NO_AVAILABLE_SEEDS"
    assert retry_entry["retry_count"] == 0
    mock_bazarr_lookup.assert_called_once()
    mock_optimize.assert_called_once()
    mock_notify_status.assert_called_once()


@patch("src.trigger.notify_status")
@patch("src.trigger.analyzer.diagnose_sync")
@patch("src.trigger.radarr_client.get_movie_by_tmdbid")
def test_run_merger_schedules_retry_for_fingerprint_low_confidence(
    mock_get_movie,
    mock_diagnose_sync,
    mock_notify_status,
    tmp_path,
):
    import src.trigger as trigger

    trigger.queue_manager = QueueManager(tmp_path / "queue.json", max_attempts=3)
    trigger.history_manager = HistoryManager(tmp_path / "history.json", max_entries=500)
    trigger.group_history_manager = GroupHistoryManager(tmp_path / "group_history.json")
    trigger.retry_queue_manager = RetryQueueManager(tmp_path / "retry_queue.json")

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
        "category": "FINGERPRINT_LOW_CONFIDENCE",
        "diff": 14.2,
        "runtime_4k": 7200.0,
        "runtime_1080p": 7214.2,
        "runtime_oficial": 7200.0,
        "offset_estimate": 14.2,
        "offset_confidence": 0.4,
    }

    run_merger(file_1080p, 0, "1368166", {"title": "The Housemaid", "year": "2025"}, False, "", candidates=[], current_index=0)

    retry_entry = trigger.retry_queue_manager.get_entry("1368166")
    assert retry_entry["reason"] == "FINGERPRINT_LOW_CONFIDENCE"
    mock_notify_status.assert_called()


@patch("src.trigger.run_analyzer")
@patch("src.trigger.radarr_client.get_movie_by_tmdbid")
def test_process_pending_retries_replays_due_entries(
    mock_get_movie,
    mock_run_analyzer,
    tmp_path,
):
    import src.trigger as trigger

    trigger.retry_queue_manager = RetryQueueManager(tmp_path / "retry_queue.json", retry_delays_hours=[1], max_attempts=3)
    trigger.queue_manager = QueueManager(tmp_path / "queue.json", max_attempts=3)

    file_4k = tmp_path / "movie4k.mkv"
    file_4k.write_text("4k")
    mock_get_movie.return_value = {
        "id": 42,
        "title": "The Housemaid",
        "year": 2025,
        "movieFile": {"path": str(file_4k)},
    }

    trigger.retry_queue_manager.schedule_retry("1368166", "NOT_FOUND")
    payload = trigger.retry_queue_manager._read()
    payload["1368166"]["next_retry_at"] = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    trigger.retry_queue_manager._write(payload)

    processed = trigger.process_pending_retries()

    assert processed == 1
    mock_run_analyzer.assert_called_once()


@patch("src.trigger.notify_status")
@patch("src.trigger.qbit_client.remove_torrent")
@patch("src.trigger.radarr_client.apply_success_tag")
@patch("src.trigger.radarr_client.rescan_movie")
@patch("src.trigger.radarr_client.get_movie_by_tmdbid")
@patch("src.trigger.analyzer.validate_recovery_attempt")
@patch("src.trigger.merger.validate_and_replace")
@patch("src.trigger.merger.mux_audio")
@patch("src.trigger.merger.extract_audio")
@patch("src.trigger.analyzer.get_ptbr_stream_index", return_value=2)
@patch("src.trigger.analyzer.diagnose_sync")
def test_run_merger_marks_manual_recovery_success(
    mock_diagnose_sync,
    _mock_stream_index,
    _mock_extract_audio,
    _mock_mux_audio,
    mock_validate_and_replace,
    mock_validate_recovery,
    mock_get_movie,
    mock_rescan_movie,
    mock_apply_success_tag,
    mock_remove_torrent,
    mock_notify_status,
    tmp_path,
):
    import src.trigger as trigger

    trigger.queue_manager = QueueManager(tmp_path / "queue.json", max_attempts=3)
    trigger.history_manager = HistoryManager(tmp_path / "history.json", max_entries=500)
    trigger.group_history_manager = GroupHistoryManager(tmp_path / "group_history.json")
    file_4k = tmp_path / "movie4k.mkv"
    file_1080p = tmp_path / "movie1080p.mkv"
    file_4k.write_text("4k")
    file_1080p.write_text("1080p")

    mock_diagnose_sync.return_value = {
        "sync_ok": False,
        "category": "OFFSET_SUSPECTED",
        "recoverability": "recoverable",
        "terminal": False,
        "preserve_candidate": True,
        "recovery_reason": "manual-offset",
        "diff": 8.4,
        "runtime_4k": 6600.0,
        "runtime_1080p": 6608.4,
        "runtime_oficial": 6600.0,
        "offset_estimate": 8.4,
        "offset_confidence": 0.9,
        "auto_offset_eligible": False,
        "auto_offset_reason": "manual-only",
        "fingerprint_recommended": False,
        "fingerprint_reason": "manual-only",
    }
    mock_get_movie.return_value = {
        "id": 49,
        "title": "Sonic the Hedgehog 3",
        "year": 2024,
        "runtime": 110,
        "movieFile": {"path": str(file_4k)},
    }
    mock_validate_recovery.return_value = {"valid": True, "reason": "RECOVERY_OFFSET_OK", "postcheck_reason": "manual-offset-ok"}
    mock_validate_and_replace.return_value = {"valid": True, "reason": "OK"}

    run_merger(
        file_1080p,
        0,
        "939243",
        {"title": "Sonic the Hedgehog 3", "year": "2024"},
        False,
        "manualhash",
        candidates=[],
        current_index=1,
        manual_request={
            "enabled": True,
            "manual_recovery": True,
            "manual_request_id": "manual-939243-1",
            "manual_candidate_index": 2,
            "manual_force_offset_seconds": -8.4,
            "manual_trim_start_seconds": 0.0,
            "manual_trim_end_seconds": 0.0,
            "manual_reuse_last_recovery": False,
            "manual_preserve_artifacts": True,
            "manual_source_path": str(file_1080p),
        },
    )

    queue_entry = trigger.queue_manager.get_entry("939243")
    history_payload = trigger.history_manager._read()

    assert queue_entry["status"] == "SUCCESS"
    assert queue_entry["phase"] == "manual-recovery"
    assert history_payload[-1]["status"] == "MANUAL_RECOVERY_SUCCESS"
    assert any(call.args[0] == "MANUAL_RECOVERY_SUCCESS" for call in mock_notify_status.call_args_list)
    mock_rescan_movie.assert_called_once_with(49)
    mock_apply_success_tag.assert_called_once_with(49)
    mock_remove_torrent.assert_called_once_with("manualhash", delete_files=True)


@patch("src.trigger.notify_status")
@patch("src.trigger.radarr_client.get_movie_by_tmdbid")
@patch("src.trigger.analyzer.diagnose_sync")
def test_run_merger_marks_manual_recovery_pending_when_no_recovery_plan(
    mock_diagnose_sync,
    mock_get_movie,
    mock_notify_status,
    tmp_path,
):
    import src.trigger as trigger

    trigger.queue_manager = QueueManager(tmp_path / "queue.json", max_attempts=3)
    trigger.history_manager = HistoryManager(tmp_path / "history.json", max_entries=500)
    trigger.group_history_manager = GroupHistoryManager(tmp_path / "group_history.json")
    file_4k = tmp_path / "movie4k.mkv"
    file_1080p = tmp_path / "movie1080p.mkv"
    file_4k.write_text("4k")
    file_1080p.write_text("1080p")

    mock_get_movie.return_value = {
        "id": 49,
        "title": "Sonic the Hedgehog 3",
        "year": 2024,
        "runtime": 110,
        "movieFile": {"path": str(file_4k)},
    }
    mock_diagnose_sync.return_value = {
        "sync_ok": False,
        "category": "CUT_MISMATCH",
        "recoverability": "terminal",
        "terminal": True,
        "preserve_candidate": False,
        "recovery_reason": "structural-cut-mismatch",
        "diff": 141.179,
        "runtime_4k": 6605.349,
        "runtime_1080p": 6746.528,
        "runtime_oficial": 6600.0,
        "offset_estimate": 141.179,
        "offset_confidence": 0.9,
        "auto_offset_eligible": False,
        "auto_offset_reason": "not-eligible",
        "fingerprint_recommended": False,
        "fingerprint_reason": "manual-only",
    }

    run_merger(
        file_1080p,
        0,
        "939243",
        {"title": "Sonic the Hedgehog 3", "year": "2024"},
        False,
        "",
        candidates=[],
        current_index=0,
        manual_request={
            "enabled": True,
            "manual_recovery": True,
            "manual_request_id": "manual-939243-1",
            "manual_candidate_index": 1,
            "manual_force_offset_seconds": None,
            "manual_trim_start_seconds": 0.0,
            "manual_trim_end_seconds": 0.0,
            "manual_reuse_last_recovery": False,
            "manual_preserve_artifacts": True,
            "manual_source_path": str(file_1080p),
        },
    )

    queue_entry = trigger.queue_manager.get_entry("939243")
    history_payload = trigger.history_manager._read()

    assert queue_entry["status"] == "PENDING"
    assert queue_entry["phase"] == "manual-recovery"
    assert history_payload[-1]["status"] == "MANUAL_RECOVERY_PENDING"
    assert any(call.args[0] == "MANUAL_RECOVERY_PENDING" for call in mock_notify_status.call_args_list)
