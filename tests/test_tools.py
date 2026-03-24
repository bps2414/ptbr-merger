import json
import os
import sys
from pathlib import Path

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
    queue_file.write_text(
        json.dumps({"680493": {"status": "FAILED", "attempts": 1}}, indent=2),
        encoding="utf-8",
    )
    history_file.write_text(
        json.dumps([{"tmdbId": "680493", "status": "FALLBACK"}], indent=2),
        encoding="utf-8",
    )

    snapshot = build_status_snapshot(queue_file=queue_file, history_file=history_file, torrent_rows=[])

    assert snapshot["queue"]["680493"]["status"] == "FAILED"
    assert snapshot["history"][-1]["status"] == "FALLBACK"
    assert snapshot["torrents"] == []


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
