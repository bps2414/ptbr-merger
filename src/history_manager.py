import json
from datetime import datetime, timezone
from pathlib import Path


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class HistoryManager:
    def __init__(self, history_file: Path, max_entries: int = 500) -> None:
        self.history_file = Path(history_file)
        self.max_entries = max_entries
        if not self.history_file.exists():
            self._write([])

    def _read(self) -> list[dict]:
        if not self.history_file.exists():
            return []
        with open(self.history_file, "r", encoding="utf-8") as file:
            data = json.load(file) or []
        return data if isinstance(data, list) else []

    def _write(self, payload: list[dict]) -> None:
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.history_file, "w", encoding="utf-8") as file:
            json.dump(payload[-self.max_entries :], file, ensure_ascii=False, indent=2)

    def append(self, event: dict) -> dict:
        events = self._read()
        payload = {"timestamp": _utc_now(), **event}
        events.append(payload)
        self._write(events)
        return payload
