import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.retry_queue_manager import RetryQueueManager


def test_retry_queue_manager_schedules_and_lists_due_entries(tmp_path: Path):
    queue_file = tmp_path / "retry_queue.json"
    manager = RetryQueueManager(queue_file, retry_delays_hours=[1, 6, 24], max_attempts=3)

    entry = manager.schedule_retry("1084242", "NO_AVAILABLE_SEEDS")

    assert entry["tmdbId"] == "1084242"
    assert entry["reason"] == "NO_AVAILABLE_SEEDS"
    assert entry["retry_count"] == 0
    assert manager.get_due_entries(now=datetime.now(timezone.utc)) == []

    payload = json.loads(queue_file.read_text(encoding="utf-8"))
    payload["1084242"]["next_retry_at"] = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    queue_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    due_entries = manager.get_due_entries(now=datetime.now(timezone.utc))
    assert [item["tmdbId"] for item in due_entries] == ["1084242"]


def test_retry_queue_manager_requeues_with_next_delay_and_removes_after_max_attempts(tmp_path: Path):
    queue_file = tmp_path / "retry_queue.json"
    manager = RetryQueueManager(queue_file, retry_delays_hours=[1, 6], max_attempts=2)

    manager.schedule_retry("939243", "NOT_FOUND")
    first = manager.bump_retry("939243")
    second = manager.bump_retry("939243")

    assert first["retry_count"] == 1
    assert second is None
    assert manager.get_entry("939243") is None
