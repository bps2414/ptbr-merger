import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class QueueManager:
    queue_file: Path
    max_attempts: int = 3

    def __post_init__(self) -> None:
        self.queue_file = Path(self.queue_file)
        if not self.queue_file.exists():
            self._write({})

    def _read(self) -> dict:
        if not self.queue_file.exists():
            return {}
        with open(self.queue_file, "r", encoding="utf-8") as f:
            return json.load(f) or {}

    def _write(self, payload: dict) -> None:
        self.queue_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.queue_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    def get_entry(self, tmdb_id: str) -> Optional[dict]:
        return self._read().get(str(tmdb_id))

    def can_process(self, tmdb_id: str) -> tuple[bool, Optional[str]]:
        entry = self.get_entry(tmdb_id)
        if not entry:
            return True, None
        status = entry.get("status")
        if status in {"PROCESSING", "SUCCESS", "ABANDONED"}:
            return False, status
        return True, status

    def begin(self, tmdb_id: str, phase: str, candidate_index: int = 0) -> dict:
        payload = self._read()
        entry = payload.get(str(tmdb_id), {})
        attempts = int(entry.get("attempts", 0) or 0)
        payload[str(tmdb_id)] = {
            "tmdbId": str(tmdb_id),
            "phase": phase,
            "candidate_index": candidate_index,
            "attempts": attempts,
            "status": "PROCESSING",
            "last_error": entry.get("last_error"),
            "updated_at": _utc_now(),
        }
        self._write(payload)
        return payload[str(tmdb_id)]

    def record_pending(self, tmdb_id: str, phase: str, candidate_index: int = 0) -> dict:
        payload = self._read()
        entry = payload.get(str(tmdb_id), {})
        payload[str(tmdb_id)] = {
            "tmdbId": str(tmdb_id),
            "phase": phase,
            "candidate_index": candidate_index,
            "attempts": int(entry.get("attempts", 0) or 0),
            "status": "PENDING",
            "last_error": entry.get("last_error"),
            "updated_at": _utc_now(),
        }
        self._write(payload)
        return payload[str(tmdb_id)]

    def record_failure(self, tmdb_id: str, phase: str, error: str, candidate_index: int = 0) -> dict:
        payload = self._read()
        entry = payload.get(str(tmdb_id), {})
        attempts = int(entry.get("attempts", 0) or 0) + 1
        status = "ABANDONED" if attempts >= self.max_attempts else "FAILED"
        payload[str(tmdb_id)] = {
            "tmdbId": str(tmdb_id),
            "phase": phase,
            "candidate_index": candidate_index,
            "attempts": attempts,
            "status": status,
            "last_error": error,
            "updated_at": _utc_now(),
        }
        self._write(payload)
        return payload[str(tmdb_id)]

    def record_success(self, tmdb_id: str, phase: str, candidate_index: int = 0) -> dict:
        payload = self._read()
        entry = payload.get(str(tmdb_id), {})
        payload[str(tmdb_id)] = {
            "tmdbId": str(tmdb_id),
            "phase": phase,
            "candidate_index": candidate_index,
            "attempts": int(entry.get("attempts", 0) or 0),
            "status": "SUCCESS",
            "last_error": None,
            "updated_at": _utc_now(),
        }
        self._write(payload)
        return payload[str(tmdb_id)]
