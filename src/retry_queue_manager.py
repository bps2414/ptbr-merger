import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _serialize_dt(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _parse_dt(value: str | None) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


@dataclass
class RetryQueueManager:
    queue_file: Path
    retry_delays_hours: list[int] | None = None
    max_attempts: int = 3

    def __post_init__(self) -> None:
        self.queue_file = Path(self.queue_file)
        self.retry_delays_hours = list(self.retry_delays_hours or [1, 6, 24])
        if not self.queue_file.exists():
            self._write({})

    def _read(self) -> dict:
        if not self.queue_file.exists():
            return {}
        with open(self.queue_file, "r", encoding="utf-8") as file:
            return json.load(file) or {}

    def _write(self, payload: dict) -> None:
        self.queue_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.queue_file, "w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)

    def get_entry(self, tmdb_id: str) -> Optional[dict]:
        return self._read().get(str(tmdb_id))

    def schedule_retry(self, tmdb_id: str, reason: str, now: datetime | None = None, metadata: Optional[dict] = None) -> dict:
        payload = self._read()
        current_now = now or _utc_now()
        entry = payload.get(str(tmdb_id), {})
        retry_count = int(entry.get("retry_count", 0) or 0)
        delay_hours = self.retry_delays_hours[min(retry_count, len(self.retry_delays_hours) - 1)]
        merged = {
            **entry,
            "tmdbId": str(tmdb_id),
            "reason": reason,
            "retry_count": retry_count,
            "next_retry_at": _serialize_dt(current_now + timedelta(hours=delay_hours)),
            "updated_at": _serialize_dt(current_now),
        }
        if metadata:
            merged.update({key: value for key, value in metadata.items() if value is not None})
        payload[str(tmdb_id)] = merged
        self._write(payload)
        return merged

    def get_due_entries(self, now: datetime | None = None) -> list[dict]:
        current_now = now or _utc_now()
        due = []
        for entry in self._read().values():
            next_retry_at = _parse_dt(entry.get("next_retry_at"))
            if next_retry_at and next_retry_at <= current_now:
                due.append(entry)
        return sorted(due, key=lambda item: item.get("next_retry_at", ""))

    def bump_retry(self, tmdb_id: str, now: datetime | None = None) -> Optional[dict]:
        payload = self._read()
        entry = payload.get(str(tmdb_id))
        if not entry:
            return None
        current_now = now or _utc_now()
        next_retry_count = int(entry.get("retry_count", 0) or 0) + 1
        if next_retry_count >= self.max_attempts:
            payload.pop(str(tmdb_id), None)
            self._write(payload)
            return None
        delay_hours = self.retry_delays_hours[min(next_retry_count, len(self.retry_delays_hours) - 1)]
        entry["retry_count"] = next_retry_count
        entry["next_retry_at"] = _serialize_dt(current_now + timedelta(hours=delay_hours))
        entry["updated_at"] = _serialize_dt(current_now)
        payload[str(tmdb_id)] = entry
        self._write(payload)
        return entry

    def remove(self, tmdb_id: str) -> None:
        payload = self._read()
        if str(tmdb_id) in payload:
            payload.pop(str(tmdb_id), None)
            self._write(payload)
