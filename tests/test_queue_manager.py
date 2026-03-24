import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.queue_manager import QueueManager


def test_queue_manager_blocks_duplicate_processing(tmp_path: Path):
    queue_file = tmp_path / "queue.json"
    manager = QueueManager(queue_file, max_attempts=3)

    entry = manager.begin("1368166", "merge", candidate_index=1)

    assert entry["status"] == "PROCESSING"
    assert entry["attempts"] == 0

    can_process, reason = manager.can_process("1368166")

    assert can_process is False
    assert reason == "PROCESSING"


def test_queue_manager_abandons_after_reaching_max_attempts(tmp_path: Path):
    queue_file = tmp_path / "queue.json"
    manager = QueueManager(queue_file, max_attempts=2)

    manager.begin("1368166", "merge", candidate_index=0)
    first = manager.record_failure("1368166", "merge", "sync mismatch", candidate_index=0)
    second = manager.record_failure("1368166", "merge", "sync mismatch", candidate_index=1)

    assert first["status"] == "FAILED"
    assert first["attempts"] == 1
    assert second["status"] == "ABANDONED"
    assert second["attempts"] == 2


def test_queue_manager_persists_success_and_skips_reprocessing(tmp_path: Path):
    queue_file = tmp_path / "queue.json"
    manager = QueueManager(queue_file, max_attempts=3)

    manager.begin("1368166", "merge", candidate_index=0)
    manager.record_success("1368166", "merge", candidate_index=0)

    reloaded = QueueManager(queue_file, max_attempts=3)
    can_process, reason = reloaded.can_process("1368166")

    assert can_process is False
    assert reason == "SUCCESS"
    assert reloaded.get_entry("1368166")["status"] == "SUCCESS"


def test_queue_manager_can_attach_metadata_to_existing_entry(tmp_path: Path):
    queue_file = tmp_path / "queue.json"
    manager = QueueManager(queue_file, max_attempts=3)

    manager.record_pending("945961", "await-download", candidate_index=0)
    entry = manager.attach_metadata("945961", discord_message_id="discord-1")

    assert entry["discord_message_id"] == "discord-1"
    assert manager.get_entry("945961")["discord_message_id"] == "discord-1"


def test_queue_manager_preserves_metadata_across_state_transitions(tmp_path: Path):
    queue_file = tmp_path / "queue.json"
    manager = QueueManager(queue_file, max_attempts=3)

    manager.record_pending("945961", "await-download", candidate_index=0)
    manager.attach_metadata("945961", discord_message_id="discord-1")
    processing = manager.begin("945961", "merge", candidate_index=1)
    success = manager.record_success("945961", "merge", candidate_index=1)

    assert processing["discord_message_id"] == "discord-1"
    assert success["discord_message_id"] == "discord-1"
