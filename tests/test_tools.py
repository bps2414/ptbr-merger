import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.tools.reset_queue_entry import reset_queue_entry
from src.tools.refresh_webhook import build_refresh_payload
from src.tools.status import build_status_snapshot
from src.tools.tail_log import read_last_lines


def test_read_last_lines_returns_requested_number_of_lines(tmp_path: Path):
    log_file = tmp_path / "ptbrmerger.log"
    log_file.write_text("a\nb\nc\n", encoding="utf-8")

    lines = read_last_lines(log_file, lines=2)

    assert lines == ["b", "c"]


def test_build_status_snapshot_reads_queue_and_history(tmp_path: Path):
    queue_file = tmp_path / "queue.json"
    history_file = tmp_path / "history.json"
    group_history_file = tmp_path / "group_history.json"
    queue_file.write_text(
        json.dumps({"680493": {"status": "FAILED", "attempts": 1}}, indent=2),
        encoding="utf-8",
    )
    history_file.write_text(
        json.dumps([{"tmdbId": "680493", "status": "FALLBACK"}], indent=2),
        encoding="utf-8",
    )
    group_history_file.write_text(
        json.dumps([{"group": "sf", "source_4k": "AMZN.WEBDL", "source_1080p": "AMZN.WEBDL", "result": "SUCCESS"}], indent=2),
        encoding="utf-8",
    )

    snapshot = build_status_snapshot(
        queue_file=queue_file,
        history_file=history_file,
        torrent_rows=[],
        group_history_file=group_history_file,
    )

    assert snapshot["queue"]["680493"]["status"] == "FAILED"
    assert snapshot["history"][-1]["status"] == "FALLBACK"
    assert snapshot["torrents"] == []
    assert snapshot["compatibility"]["top_groups"][0]["group"] == "sf"


def test_reset_queue_entry_removes_specific_tmdb_id(tmp_path: Path):
    queue_file = tmp_path / "queue.json"
    queue_file.write_text(
        json.dumps(
            {
                "680493": {"status": "ABANDONED"},
                "1368166": {"status": "SUCCESS"},
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    reset_queue_entry(queue_file, "680493")

    contents = json.loads(queue_file.read_text(encoding="utf-8"))
    assert "680493" not in contents
    assert contents["1368166"]["status"] == "SUCCESS"


def test_build_refresh_payload_uses_queue_history_and_torrent_state():
    phase, context = build_refresh_payload(
        entry={
            "tmdbId": "945961",
            "phase": "await-download",
            "candidate_index": 1,
            "discord_message_id": "discord-1",
        },
        movie={
            "title": "Alien: Romulus",
            "year": 2024,
            "images": [
                {"coverType": "poster", "remoteUrl": "https://image.example/poster.jpg"},
                {"coverType": "fanart", "remoteUrl": "https://image.example/fanart.jpg"},
            ],
        },
        events=[
            {
                "tmdbId": "945961",
                "release_title": "Alien.Romulus.2024.1080p.WEB-DL.DUAL.5.1",
                "indexer": "Catálogo Betor",
                "sync_diff": 0.0,
                "offset_estimate": 0.0,
                "fingerprint_category": "FINGERPRINT_OFFSET_OK",
                "fingerprint_confidence": 0.91,
            }
        ],
        torrent={
            "progress": 64.2,
            "eta": 394,
            "state": "downloading",
            "num_seeds": 4,
            "num_leechs": 2,
        },
    )

    assert phase == "download-await"
    assert context["title"] == "Alien: Romulus"
    assert context["release_title"].startswith("Alien.Romulus")
    assert context["progress_percent"] == 64
    assert context["eta_seconds"] == 394
    assert context["qbit_state"] == "downloading"
    assert context["num_seeds"] == 4
    assert context["fingerprint_category"] == "FINGERPRINT_OFFSET_OK"


@patch("src.tools.refresh_webhook.notify_status")
@patch("src.tools.refresh_webhook.radarr_client.get_movie_by_tmdbid")
@patch("src.tools.refresh_webhook.qbit_client.list_ptbr_torrents")
def test_refresh_webhooks_updates_terminal_skipped_entry(
    mock_list_ptbr_torrents,
    mock_get_movie,
    mock_notify_status,
    tmp_path: Path,
):
    import src.tools.refresh_webhook as refresh_webhook

    queue_file = tmp_path / "queue.json"
    history_file = tmp_path / "history.json"
    queue_file.write_text(
        json.dumps(
            {
                "1084242": {
                    "tmdbId": "1084242",
                    "phase": "analyzer",
                    "candidate_index": 0,
                    "attempts": 0,
                    "status": "SUCCESS",
                    "discord_message_id": "discord-final",
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    history_file.write_text(
        json.dumps(
            [
                {
                    "tmdbId": "1084242",
                    "title": "Zootopia 2",
                    "year": "2025",
                    "status": "SKIPPED_HAS_PTBR",
                    "phase": "analyzer",
                }
            ],
            indent=2,
        ),
        encoding="utf-8",
    )
    mock_get_movie.return_value = {"title": "Zootopia 2", "year": 2025, "images": []}
    mock_list_ptbr_torrents.return_value = []

    original_base_dir = refresh_webhook.BASE_DIR
    refresh_webhook.BASE_DIR = tmp_path
    try:
        updated = refresh_webhook.refresh_webhooks(tmdb_id="1084242")
    finally:
        refresh_webhook.BASE_DIR = original_base_dir

    assert updated == 1
    mock_notify_status.assert_called_once()
    assert mock_notify_status.call_args.args[0] == "SKIPPED_HAS_PTBR"
    assert mock_notify_status.call_args.args[1]["discord_message_id"] == "discord-final"


@patch("src.tools.refresh_webhook.notify_status")
@patch("src.tools.refresh_webhook.radarr_client.get_movie_by_tmdbid")
@patch("src.tools.refresh_webhook.qbit_client.list_ptbr_torrents")
def test_refresh_webhooks_can_create_terminal_message_from_history_without_queue_entry(
    mock_list_ptbr_torrents,
    mock_get_movie,
    mock_notify_status,
    tmp_path: Path,
):
    import src.tools.refresh_webhook as refresh_webhook

    history_file = tmp_path / "history.json"
    history_file.write_text(
        json.dumps(
            [
                {
                    "tmdbId": "1084242",
                    "title": "Zootopia 2",
                    "year": "2025",
                    "status": "SKIPPED_HAS_PTBR",
                    "phase": "analyzer",
                }
            ],
            indent=2,
        ),
        encoding="utf-8",
    )
    mock_get_movie.return_value = {"title": "Zootopia 2", "year": 2025, "images": []}
    mock_list_ptbr_torrents.return_value = []

    def _notify(status, context):
        context["discord_message_id"] = "discord-created"

    mock_notify_status.side_effect = _notify

    original_base_dir = refresh_webhook.BASE_DIR
    refresh_webhook.BASE_DIR = tmp_path
    try:
        updated = refresh_webhook.refresh_webhooks(tmdb_id="1084242")
    finally:
        refresh_webhook.BASE_DIR = original_base_dir

    assert updated == 1
    mock_notify_status.assert_called_once()
    queue_payload = json.loads((tmp_path / "queue.json").read_text(encoding="utf-8"))
    assert queue_payload["1084242"]["status"] == "SUCCESS"
    assert queue_payload["1084242"]["discord_message_id"] == "discord-created"
