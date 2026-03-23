import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.history_manager import HistoryManager


def test_history_manager_appends_events(tmp_path: Path):
    history = HistoryManager(tmp_path / "history.json", max_entries=5)

    event = history.append({"tmdbId": "1368166", "status": "SUCCESS"})

    assert event["tmdbId"] == "1368166"
    assert event["status"] == "SUCCESS"
    assert "timestamp" in event


def test_history_manager_respects_retention_limit(tmp_path: Path):
    history = HistoryManager(tmp_path / "history.json", max_entries=2)

    history.append({"tmdbId": "1", "status": "A"})
    history.append({"tmdbId": "2", "status": "B"})
    history.append({"tmdbId": "3", "status": "C"})

    contents = history._read()
    assert len(contents) == 2
    assert [item["tmdbId"] for item in contents] == ["2", "3"]
