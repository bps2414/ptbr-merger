from __future__ import annotations

import json
import os
import shutil
import threading
import uuid
from pathlib import Path
from typing import Any


_WRITE_LOCK = threading.RLock()


class JsonStore:
    def __init__(self, path: Path, *, default_data: dict[str, Any], schema_version: int) -> None:
        self.path = Path(path)
        self.default_data = dict(default_data)
        self.schema_version = int(schema_version)
        with _WRITE_LOCK:
            if not self.path.exists():
                self.write(self.default_data, create_backup=False)

    def _with_schema(self, payload: dict[str, Any]) -> dict[str, Any]:
        merged = dict(payload)
        merged["schema_version"] = self.schema_version
        return merged

    def read(self) -> dict[str, Any]:
        if not self.path.exists():
            return self._with_schema(self.default_data)
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            corrupt_path = self.path.with_suffix(self.path.suffix + ".corrupt")
            try:
                shutil.copy2(self.path, corrupt_path)
            except OSError:
                pass
            return self._with_schema(self.default_data)
        if not isinstance(payload, dict):
            return self._with_schema(self.default_data)
        payload.setdefault("schema_version", self.schema_version)
        return payload

    def write(self, payload: dict[str, Any], *, create_backup: bool = True) -> dict[str, Any]:
        with _WRITE_LOCK:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            final_payload = self._with_schema(payload)
            if create_backup and self.path.exists():
                shutil.copy2(self.path, self.path.with_suffix(self.path.suffix + ".bak"))
            tmp_path = self.path.with_name(f"{self.path.name}.{uuid.uuid4().hex}.tmp")
            tmp_path.write_text(json.dumps(final_payload, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp_path, self.path)
            return final_payload
