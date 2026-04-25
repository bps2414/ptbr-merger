import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.tools.preflight import run_preflight
from src.tools.reset_queue_entry import reset_queue_entry
from src.tools.refresh_webhook import build_refresh_payload
from src.tools.runtime_hygiene import apply_runtime_hygiene, build_runtime_hygiene_plan
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
    retry_queue_file = tmp_path / "retry_queue.json"
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
    retry_queue_file.write_text(
        json.dumps({"680493": {"reason": "NO_AVAILABLE_SEEDS", "retry_count": 0}}, indent=2),
        encoding="utf-8",
    )

    snapshot = build_status_snapshot(
        queue_file=queue_file,
        history_file=history_file,
        torrent_rows=[],
        group_history_file=group_history_file,
        retry_queue_file=retry_queue_file,
    )

    assert snapshot["queue"]["680493"]["status"] == "FAILED"
    assert snapshot["history"][-1]["status"] == "FALLBACK"
    assert snapshot["torrents"] == []
    assert snapshot["compatibility"]["top_groups"][0]["group"] == "sf"
    assert snapshot["retry_queue"]["680493"]["reason"] == "NO_AVAILABLE_SEEDS"


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


def test_build_runtime_hygiene_plan_reports_targets(tmp_path: Path):
    queue_file = tmp_path / "queue.json"
    queue_file.write_text("{}", encoding="utf-8")

    plan = build_runtime_hygiene_plan([queue_file], tmp_path / ".runtime-archive")

    assert plan["archive_root"].endswith(".runtime-archive")
    assert plan["files"][0]["exists"] is True
    assert plan["files"][0]["reset_to"] == "dict"


def test_apply_runtime_hygiene_archives_and_resets_files(tmp_path: Path):
    queue_file = tmp_path / "queue.json"
    history_file = tmp_path / "history.json"
    queue_file.write_text(json.dumps({"939243": {"status": "FAILED"}}, indent=2), encoding="utf-8")
    history_file.write_text(json.dumps([{"tmdbId": "939243"}], indent=2), encoding="utf-8")

    result = apply_runtime_hygiene([queue_file, history_file], tmp_path / ".runtime-archive")

    assert Path(result["archive_dir"]).exists()
    assert json.loads(queue_file.read_text(encoding="utf-8")) == {}
    assert json.loads(history_file.read_text(encoding="utf-8")) == []
    assert all(item["reset"] is True for item in result["results"])


@patch("src.tools.preflight.qbit_login")
@patch("src.tools.preflight.requests.get")
def test_run_preflight_reports_warns_and_blockers(mock_get, mock_qbit_login, tmp_path: Path):
    queue_file = tmp_path / "queue.json"
    history_file = tmp_path / "history.json"
    group_history_file = tmp_path / "group_history.json"
    retry_queue_file = tmp_path / "retry_queue.json"
    temp_root = tmp_path / "temp-root"
    temp_root.mkdir()
    queue_file.write_text("{}", encoding="utf-8")
    history_file.write_text("[]", encoding="utf-8")
    group_history_file.write_text("[]", encoding="utf-8")
    retry_queue_file.write_text("{}", encoding="utf-8")

    cfg = SimpleNamespace(
        ffmpeg=SimpleNamespace(ffmpeg_path="python", ffprobe_path="python"),
        radarr=SimpleNamespace(
            url="http://localhost:7878",
            api_key="token",
            ptbrmerger_root_folder=str(temp_root),
        ),
        qbittorrent=SimpleNamespace(url="http://localhost:8080"),
        bazarr=SimpleNamespace(url="", api_key="", language="pt-BR"),
        notifications=SimpleNamespace(discord_webhook_url=""),
        processing=SimpleNamespace(queue_file=queue_file.name),
        retry=SimpleNamespace(queue_file=retry_queue_file.name),
        logging=SimpleNamespace(history_file=history_file.name, group_history_file=group_history_file.name),
    )

    radarr_response = SimpleNamespace(
        status_code=200,
        text='{"version":"5.0.0"}',
        json=lambda: {"version": "5.0.0"},
        raise_for_status=lambda: None,
    )

    def _request(url, **kwargs):
        if url.endswith("/api/v3/system/status"):
            return radarr_response
        raise requests.exceptions.ConnectionError("unexpected-url")

    mock_get.side_effect = _request
    mock_qbit_login.return_value = None

    with patch("src.tools.preflight.get_config", return_value=cfg):
        report = run_preflight(base_dir=tmp_path)

    statuses = {check["name"]: check["status"] for check in report["checks"]}
    assert report["status"] == "BLOCKER"
    assert statuses["ffmpeg"] == "OK"
    assert statuses["ffprobe"] == "OK"
    assert statuses["radarr"] == "OK"
    assert statuses["qbittorrent"] == "BLOCKER"
    assert statuses["bazarr"] == "WARN"
    assert statuses["discord"] == "WARN"


@patch("src.tools.preflight.qbit_login")
@patch("src.tools.preflight.requests.get")
def test_run_preflight_flags_placeholder_configuration(mock_get, mock_qbit_login, tmp_path: Path):
    queue_file = tmp_path / "queue.json"
    history_file = tmp_path / "history.json"
    group_history_file = tmp_path / "group_history.json"
    retry_queue_file = tmp_path / "retry_queue.json"
    temp_root = tmp_path / "temp-root"
    temp_root.mkdir()
    queue_file.write_text("{}", encoding="utf-8")
    history_file.write_text("[]", encoding="utf-8")
    group_history_file.write_text("[]", encoding="utf-8")
    retry_queue_file.write_text("{}", encoding="utf-8")

    cfg = SimpleNamespace(
        ffmpeg=SimpleNamespace(ffmpeg_path=sys.executable, ffprobe_path=sys.executable),
        radarr=SimpleNamespace(
            url="http://localhost:7878",
            api_key="CHANGE_ME",
            ptbrmerger_root_folder=str(temp_root),
        ),
        qbittorrent=SimpleNamespace(url="http://localhost:8080", username="CHANGE_ME", password="CHANGE_ME"),
        bazarr=SimpleNamespace(url="", api_key="", language="pt-BR"),
        notifications=SimpleNamespace(discord_webhook_url="https://discord.invalid/webhook"),
        processing=SimpleNamespace(queue_file=queue_file.name),
        retry=SimpleNamespace(queue_file=retry_queue_file.name),
        logging=SimpleNamespace(history_file=history_file.name, group_history_file=group_history_file.name),
    )

    with patch("src.tools.preflight.get_config", return_value=cfg):
        report = run_preflight(base_dir=tmp_path)

    checks = {check["name"]: check for check in report["checks"]}
    assert report["status"] == "BLOCKER"
    assert checks["radarr"]["message"] == "placeholder-api-key"
    assert checks["qbittorrent"]["message"] == "placeholder-credentials"
    assert checks["discord"]["message"] == "placeholder-url"
    mock_get.assert_not_called()
    mock_qbit_login.assert_not_called()


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


def test_build_status_snapshot_collects_manual_recovery_entries(tmp_path: Path):
    queue_file = tmp_path / "queue.json"
    history_file = tmp_path / "history.json"
    retry_queue_file = tmp_path / "retry_queue.json"
    queue_file.write_text(
        json.dumps(
            {
                "939243": {
                    "tmdbId": "939243",
                    "status": "PENDING",
                    "phase": "manual-recovery",
                    "manual_recovery": True,
                    "manual_request_id": "manual-939243-1",
                    "manual_force_offset_seconds": -8.4,
                    "manual_source_path": r"D:\downloads\Sonic.3.1080p\movie.mkv",
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    history_file.write_text("[]", encoding="utf-8")
    retry_queue_file.write_text("{}", encoding="utf-8")

    snapshot = build_status_snapshot(
        queue_file=queue_file,
        history_file=history_file,
        torrent_rows=[],
        retry_queue_file=retry_queue_file,
    )

    assert snapshot["manual_recoveries"][0]["tmdbId"] == "939243"
    assert snapshot["manual_recoveries"][0]["manual_request_id"] == "manual-939243-1"
    assert snapshot["manual_recoveries"][0]["manual_force_offset_seconds"] == -8.4


def test_build_refresh_payload_includes_manual_recovery_context():
    phase, context = build_refresh_payload(
        entry={
            "tmdbId": "939243",
            "phase": "manual-recovery",
            "status": "PENDING",
            "manual_recovery": True,
            "manual_request_id": "manual-939243-1",
            "manual_source_path": r"D:\downloads\Sonic.3.1080p\movie.mkv",
            "manual_force_offset_seconds": -8.4,
        },
        movie={"title": "Sonic the Hedgehog 3", "year": 2024, "images": []},
        events=[
            {
                "tmdbId": "939243",
                "status": "MANUAL_RECOVERY_PENDING",
                "manual_recovery": True,
                "manual_request_id": "manual-939243-1",
                "manual_trim_end_seconds": 24.0,
                "recovery_strategy": "edge-trim",
                "recovery_validation_reason": "RECOVERY_EDGE_TRIM_OK",
            }
        ],
        torrent=None,
    )

    assert phase == "merge-start"
    assert context["manual_request_id"] == "manual-939243-1"
    assert context["manual_force_offset_seconds"] == -8.4
    assert context["manual_trim_end_seconds"] == 24.0
    assert context["recovery_strategy"] == "edge-trim"


@patch("src.tools.refresh_webhook.notify_status")
@patch("src.tools.refresh_webhook.radarr_client.get_movie_by_tmdbid")
@patch("src.tools.refresh_webhook.qbit_client.list_ptbr_torrents")
def test_refresh_webhooks_recreates_manual_terminal_state_from_history(
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
                    "tmdbId": "939243",
                    "title": "Sonic the Hedgehog 3",
                    "year": "2024",
                    "status": "MANUAL_RECOVERY_SUCCESS",
                    "phase": "manual-recovery",
                    "manual_recovery": True,
                    "manual_request_id": "manual-939243-1",
                    "manual_source_path": r"D:\downloads\Sonic.3.1080p\movie.mkv",
                }
            ],
            indent=2,
        ),
        encoding="utf-8",
    )
    mock_get_movie.return_value = {"title": "Sonic the Hedgehog 3", "year": 2024, "images": []}
    mock_list_ptbr_torrents.return_value = []

    def _notify(status, context):
        context["discord_message_id"] = "discord-manual"

    mock_notify_status.side_effect = _notify

    original_base_dir = refresh_webhook.BASE_DIR
    refresh_webhook.BASE_DIR = tmp_path
    try:
        updated = refresh_webhook.refresh_webhooks(tmdb_id="939243")
    finally:
        refresh_webhook.BASE_DIR = original_base_dir

    assert updated == 1
    assert mock_notify_status.call_args.args[0] == "MANUAL_RECOVERY_SUCCESS"
    queue_payload = json.loads((tmp_path / "queue.json").read_text(encoding="utf-8"))
    assert queue_payload["939243"]["status"] == "SUCCESS"
    assert queue_payload["939243"]["phase"] == "manual-recovery"
