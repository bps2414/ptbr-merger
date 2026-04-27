import json
from pathlib import Path

from src.storage.json_store import JsonStore


def test_json_store_initializes_versioned_payload(tmp_path: Path):
    store = JsonStore(tmp_path / "jobs.json", default_data={"items": []}, schema_version=1)

    payload = store.read()

    assert payload == {"schema_version": 1, "items": []}
    assert (tmp_path / "jobs.json").exists()


def test_json_store_writes_atomically_and_keeps_backup(tmp_path: Path):
    store = JsonStore(tmp_path / "recipes.json", default_data={"items": []}, schema_version=1)
    store.write({"items": [{"id": "recipe-1"}]})

    payload = json.loads((tmp_path / "recipes.json").read_text(encoding="utf-8"))

    assert payload["schema_version"] == 1
    assert payload["items"] == [{"id": "recipe-1"}]
    assert (tmp_path / "recipes.json.bak").exists()


def test_json_store_returns_safe_default_for_corrupt_file(tmp_path: Path):
    path = tmp_path / "profiles.json"
    path.write_text("{not-json", encoding="utf-8")
    store = JsonStore(path, default_data={"items": []}, schema_version=1)

    payload = store.read()

    assert payload == {"schema_version": 1, "items": []}
    assert (tmp_path / "profiles.json.corrupt").exists()
