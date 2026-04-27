# Local Media Workflow Hub v0.5 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the current local web recovery mode into the main surface of a local media workflow hub, with one real workflow: add and automatically sync preferred-language audio into a local MKV while preserving safe output, recipes, reports, and a simple execution history.

**Architecture:** Keep the legacy Radarr/qBittorrent trigger pipeline working but do not migrate it in this phase. Add small domain models, local JSON stores with atomic writes, and a workflow module that the web API calls instead of letting `src/web/ops.py` own all product behavior. The UI should look like a hub in progress: Inicio, Workflows, Fila, Arquivos locais, Receitas, Perfis, Ferramentas, Configuracoes.

**Tech Stack:** Python 3.11+, stdlib HTTP server, plain HTML/CSS/JS, FFmpeg/FFprobe through existing `src.analyzer` and `src.merger`, JSON state under the local workspace, pytest.

---

## Product Decision

The product direction is no longer "PTBRMerger with a UI". The correct shape is:

> Local media workflow hub with one complete workflow today.

The app should expose a future-facing structure without pretending to already replace Radarr, Prowlarr, Sonarr, trackers, indexers, or qBittorrent automation.

Use these UI labels:

- `Fluxos` for workflows
- `Tarefas` for jobs
- `Receitas` for recipes
- `Relatorios` for reports
- `Perfil de idioma` for language preference
- `Arquivos locais` for input/output/workspace files
- `Ferramentas` for support and maintenance helpers

Internal code may use English names: `workflow`, `job`, `recipe`, `language_profile`, `workspace`.

## File Structure

Create:

- `src/domain/__init__.py`
  - Domain package marker.
- `src/domain/media_workflow.py`
  - Dataclasses and enums for workflows, jobs, recipes, language profiles, sync review, and operation plans.
- `src/storage/__init__.py`
  - Storage package marker.
- `src/storage/json_store.py`
  - Atomic JSON read/write helper with backup and schema version support.
- `src/storage/workflow_state.py`
  - Job, recipe, and language profile stores built on `JsonStore`.
- `src/workflows/__init__.py`
  - Workflow package marker.
- `src/workflows/preferred_audio_merge.py`
  - The first real workflow: inspect target/source, plan preferred audio mux, run sync-aware mux, validate, and record job/recipe.
- `tests/test_domain_media_workflow.py`
  - Domain serialization and defaults.
- `tests/test_storage_json_store.py`
  - Atomic writes, backups, corrupted JSON handling, schema shape.
- `tests/test_workflow_state.py`
  - Job/recipe/profile store behavior.
- `tests/test_preferred_audio_merge_workflow.py`
  - Workflow planning, sync suggestion, safe run orchestration with mocks.
- `tests/test_web_static.py`
  - Static UI vocabulary and navigation checks.

Modify:

- `src/web/ops.py`
  - Delegate new workflow behavior to `src.workflows.preferred_audio_merge`; keep existing dependency/workspace helpers.
- `src/web/server.py`
  - Add endpoints for workflows, jobs, recipes, language profiles, and support package.
- `src/web/static/index.html`
  - Reshape navigation to hub language.
- `src/web/static/app.js`
  - Load workflows/jobs/recipes/profiles and drive the preferred audio workflow.
- `src/web/static/styles.css`
  - Support the new hub layout without card-soup/dashboard analytics.
- `START_PTBRMERGER.bat`
  - Keep thin launcher; call the PowerShell launcher.
- `scripts/start-ptbrmerger-hidden.ps1`
  - Harden Python detection and user-facing launch errors.
- `README.md`
  - Reframe product as evolving local media workflow hub.
- `.planning/PROJECT.md`
  - Update "What This Is", current milestone, and out-of-scope.
- `.planning/ROADMAP.md`
  - Add v0.5 as the next milestone after post-format recovery.

Do not modify:

- `src/trigger.py` except if a test proves a narrow compatibility shim is required.
- `src/radarr_client.py` except for test-only import compatibility if required.
- qBittorrent/Radarr/Bazarr behavior.

---

### Task 1: Add Domain Models For Workflows, Jobs, Recipes, And Profiles

**Files:**
- Create: `src/domain/__init__.py`
- Create: `src/domain/media_workflow.py`
- Test: `tests/test_domain_media_workflow.py`

- [ ] **Step 1: Write failing domain tests**

Create `tests/test_domain_media_workflow.py`:

```python
from src.domain.media_workflow import (
    JobStatus,
    LanguageProfile,
    OperationPlan,
    Recipe,
    SyncReview,
    WorkflowJob,
    default_language_profile,
)


def test_default_language_profile_is_not_ptbr_hardcoded_in_the_model_name():
    profile = default_language_profile()

    assert profile.id == "pt-BR-default"
    assert profile.label == "Portugues Brasil"
    assert profile.preferred_audio_language == "pt-BR"
    assert profile.accept_dual_audio is True
    assert profile.keep_original_audio is True
    assert profile.priority == "dubbed-first"


def test_workflow_job_serializes_for_json_store():
    job = WorkflowJob(
        id="job-1",
        workflow_id="preferred-audio-merge",
        status=JobStatus.READY_FOR_REVIEW,
        target_name="target.mkv",
        source_name="source.mkv",
        recipe_id="recipe-1",
        created_at="2026-04-27T00:00:00+00:00",
        updated_at="2026-04-27T00:00:00+00:00",
    )

    payload = job.to_dict()

    assert payload["id"] == "job-1"
    assert payload["workflow_id"] == "preferred-audio-merge"
    assert payload["status"] == "ready_for_review"
    assert payload["recipe_id"] == "recipe-1"


def test_operation_plan_carries_sync_review_without_manual_values_by_default():
    sync = SyncReview(
        status="ok",
        confidence=0.88,
        suggested_offset_seconds=1.25,
        suggested_trim_start_seconds=0.0,
        suggested_trim_end_seconds=0.0,
        reason="fingerprint-offset-ok",
        duration_diff_seconds=1.25,
    )
    plan = OperationPlan(
        id="plan-1",
        workflow_id="preferred-audio-merge",
        target_path="D:/input/target.mkv",
        source_path="D:/input/source.mkv",
        output_path="D:/output/target.preferred.mkv",
        language_profile_id="pt-BR-default",
        ptbr_stream_index=2,
        sync_review=sync,
    )

    payload = plan.to_dict()

    assert payload["sync_review"]["status"] == "ok"
    assert payload["sync_review"]["suggested_offset_seconds"] == 1.25
    assert payload["manual_offset_seconds"] is None
    assert payload["will_replace_original"] is False


def test_recipe_uses_safe_user_facing_summary():
    recipe = Recipe(
        id="recipe-1",
        job_id="job-1",
        workflow_id="preferred-audio-merge",
        label="Adicionar audio a uma midia",
        target_name="target.mkv",
        source_name="source.mkv",
        output_name="target.preferred.mkv",
        language_profile_id="pt-BR-default",
        sync_summary="Offset automatico aplicado: 1.250s",
        validation_status="SUCCESS",
        report_path="D:/reports/job-1.report.json",
        output_path="D:/output/target.preferred.mkv",
        created_at="2026-04-27T00:00:00+00:00",
    )

    payload = recipe.to_dict()

    assert payload["label"] == "Adicionar audio a uma midia"
    assert payload["contains_absolute_paths"] is False
    assert payload["output_name"] == "target.preferred.mkv"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
py -3 -m pytest -q tests/test_domain_media_workflow.py
```

Expected:

```text
ModuleNotFoundError: No module named 'src.domain'
```

- [ ] **Step 3: Create the domain package**

Create `src/domain/__init__.py`:

```python
"""Domain models for local media workflows."""
```

- [ ] **Step 4: Implement domain models**

Create `src/domain/media_workflow.py`:

```python
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any


class JobStatus(str, Enum):
    QUEUED = "queued"
    READY_FOR_REVIEW = "ready_for_review"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    NEEDS_ACTION = "needs_action"


@dataclass(frozen=True)
class LanguageProfile:
    id: str
    label: str
    preferred_audio_language: str
    accept_dual_audio: bool
    keep_original_audio: bool
    priority: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def default_language_profile() -> LanguageProfile:
    return LanguageProfile(
        id="pt-BR-default",
        label="Portugues Brasil",
        preferred_audio_language="pt-BR",
        accept_dual_audio=True,
        keep_original_audio=True,
        priority="dubbed-first",
    )


@dataclass(frozen=True)
class SyncReview:
    status: str
    confidence: float
    suggested_offset_seconds: float | None
    suggested_trim_start_seconds: float
    suggested_trim_end_seconds: float
    reason: str
    duration_diff_seconds: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class OperationPlan:
    id: str
    workflow_id: str
    target_path: str
    source_path: str
    output_path: str
    language_profile_id: str
    ptbr_stream_index: int
    sync_review: SyncReview
    manual_offset_seconds: float | None = None
    manual_trim_start_seconds: float = 0.0
    manual_trim_end_seconds: float = 0.0
    will_replace_original: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["sync_review"] = self.sync_review.to_dict()
        return payload


@dataclass(frozen=True)
class WorkflowJob:
    id: str
    workflow_id: str
    status: JobStatus
    target_name: str
    source_name: str
    recipe_id: str | None
    created_at: str
    updated_at: str
    last_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = self.status.value
        return payload


@dataclass(frozen=True)
class Recipe:
    id: str
    job_id: str
    workflow_id: str
    label: str
    target_name: str
    source_name: str
    output_name: str
    language_profile_id: str
    sync_summary: str
    validation_status: str
    report_path: str
    output_path: str
    created_at: str
    contains_absolute_paths: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
```

- [ ] **Step 5: Run test to verify it passes**

Run:

```bash
py -3 -m pytest -q tests/test_domain_media_workflow.py
```

Expected:

```text
4 passed
```

- [ ] **Step 6: Commit**

```bash
git add src/domain/__init__.py src/domain/media_workflow.py tests/test_domain_media_workflow.py
git commit -m "feat: add media workflow domain models"
```

---

### Task 2: Add Atomic JSON Storage For User-Friendly Local State

**Files:**
- Create: `src/storage/__init__.py`
- Create: `src/storage/json_store.py`
- Test: `tests/test_storage_json_store.py`

- [ ] **Step 1: Write failing storage tests**

Create `tests/test_storage_json_store.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
py -3 -m pytest -q tests/test_storage_json_store.py
```

Expected:

```text
ModuleNotFoundError: No module named 'src.storage'
```

- [ ] **Step 3: Create storage package**

Create `src/storage/__init__.py`:

```python
"""Local state storage helpers."""
```

- [ ] **Step 4: Implement atomic JSON store**

Create `src/storage/json_store.py`:

```python
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any


class JsonStore:
    def __init__(self, path: Path, *, default_data: dict[str, Any], schema_version: int) -> None:
        self.path = Path(path)
        self.default_data = dict(default_data)
        self.schema_version = int(schema_version)
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
        self.path.parent.mkdir(parents=True, exist_ok=True)
        final_payload = self._with_schema(payload)
        if create_backup and self.path.exists():
            shutil.copy2(self.path, self.path.with_suffix(self.path.suffix + ".bak"))
        tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(final_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp_path, self.path)
        return final_payload
```

- [ ] **Step 5: Run test to verify it passes**

Run:

```bash
py -3 -m pytest -q tests/test_storage_json_store.py
```

Expected:

```text
3 passed
```

- [ ] **Step 6: Commit**

```bash
git add src/storage/__init__.py src/storage/json_store.py tests/test_storage_json_store.py
git commit -m "feat: add atomic json workflow storage"
```

---

### Task 3: Add Job, Recipe, And Language Profile Stores

**Files:**
- Create: `src/storage/workflow_state.py`
- Test: `tests/test_workflow_state.py`

- [ ] **Step 1: Write failing workflow state tests**

Create `tests/test_workflow_state.py`:

```python
from pathlib import Path

from src.domain.media_workflow import JobStatus, Recipe, WorkflowJob
from src.storage.workflow_state import WorkflowState


def test_workflow_state_creates_default_language_profile(tmp_path: Path):
    state = WorkflowState(tmp_path)

    profiles = state.list_language_profiles()

    assert profiles[0]["id"] == "pt-BR-default"
    assert profiles[0]["preferred_audio_language"] == "pt-BR"


def test_workflow_state_upserts_jobs_and_recipes(tmp_path: Path):
    state = WorkflowState(tmp_path)
    job = WorkflowJob(
        id="job-1",
        workflow_id="preferred-audio-merge",
        status=JobStatus.DONE,
        target_name="target.mkv",
        source_name="source.mkv",
        recipe_id="recipe-1",
        created_at="2026-04-27T00:00:00+00:00",
        updated_at="2026-04-27T00:00:00+00:00",
    )
    recipe = Recipe(
        id="recipe-1",
        job_id="job-1",
        workflow_id="preferred-audio-merge",
        label="Adicionar audio a uma midia",
        target_name="target.mkv",
        source_name="source.mkv",
        output_name="target.preferred.mkv",
        language_profile_id="pt-BR-default",
        sync_summary="Sem offset automatico necessario",
        validation_status="SUCCESS",
        report_path="D:/reports/job-1.report.json",
        output_path="D:/output/target.preferred.mkv",
        created_at="2026-04-27T00:00:00+00:00",
    )

    state.upsert_job(job)
    state.upsert_recipe(recipe)

    assert state.list_jobs()[0]["id"] == "job-1"
    assert state.list_recipes()[0]["id"] == "recipe-1"
    assert state.get_recipe("recipe-1")["target_name"] == "target.mkv"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
py -3 -m pytest -q tests/test_workflow_state.py
```

Expected:

```text
ModuleNotFoundError: No module named 'src.storage.workflow_state'
```

- [ ] **Step 3: Implement workflow state stores**

Create `src/storage/workflow_state.py`:

```python
from __future__ import annotations

from pathlib import Path

from src.domain.media_workflow import Recipe, WorkflowJob, default_language_profile
from src.storage.json_store import JsonStore


class WorkflowState:
    def __init__(self, root: Path) -> None:
        state_dir = Path(root) / "workdir" / "state"
        self.jobs = JsonStore(state_dir / "jobs.json", default_data={"items": []}, schema_version=1)
        self.recipes = JsonStore(state_dir / "recipes.json", default_data={"items": []}, schema_version=1)
        self.language_profiles = JsonStore(
            state_dir / "language_profiles.json",
            default_data={"items": [default_language_profile().to_dict()]},
            schema_version=1,
        )

    @staticmethod
    def _upsert(store: JsonStore, item: dict) -> dict:
        payload = store.read()
        items = [row for row in payload.get("items", []) if row.get("id") != item.get("id")]
        items.append(item)
        return store.write({"items": items})

    def list_jobs(self) -> list[dict]:
        return list(self.jobs.read().get("items", []))

    def upsert_job(self, job: WorkflowJob) -> dict:
        return self._upsert(self.jobs, job.to_dict())

    def list_recipes(self) -> list[dict]:
        return list(self.recipes.read().get("items", []))

    def get_recipe(self, recipe_id: str) -> dict | None:
        for recipe in self.list_recipes():
            if recipe.get("id") == recipe_id:
                return recipe
        return None

    def upsert_recipe(self, recipe: Recipe) -> dict:
        return self._upsert(self.recipes, recipe.to_dict())

    def list_language_profiles(self) -> list[dict]:
        profiles = list(self.language_profiles.read().get("items", []))
        if profiles:
            return profiles
        default_profile = default_language_profile().to_dict()
        self.language_profiles.write({"items": [default_profile]})
        return [default_profile]
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
py -3 -m pytest -q tests/test_workflow_state.py
```

Expected:

```text
2 passed
```

- [ ] **Step 5: Commit**

```bash
git add src/storage/workflow_state.py tests/test_workflow_state.py
git commit -m "feat: persist local workflow jobs and recipes"
```

---

### Task 4: Extract Preferred Audio Merge Workflow

**Files:**
- Create: `src/workflows/__init__.py`
- Create: `src/workflows/preferred_audio_merge.py`
- Test: `tests/test_preferred_audio_merge_workflow.py`

- [ ] **Step 1: Write failing workflow tests**

Create `tests/test_preferred_audio_merge_workflow.py`:

```python
from pathlib import Path
from unittest.mock import patch

from src.web.ops import ensure_workspace
from src.workflows.preferred_audio_merge import build_preferred_audio_plan, run_preferred_audio_plan


def test_build_preferred_audio_plan_includes_sync_review(tmp_path: Path):
    workspace = ensure_workspace(tmp_path)
    target = workspace.input_dir / "target.mkv"
    source = workspace.input_dir / "source.mkv"
    target.write_bytes(b"target")
    source.write_bytes(b"source")

    with patch("src.workflows.preferred_audio_merge.inspect_media_file") as inspect, \
        patch("src.workflows.preferred_audio_merge.analyzer.diagnose_sync") as diagnose:
        inspect.side_effect = [
            {"exists": True, "path": str(target), "name": "target.mkv", "has_ptbr_audio": False, "streams": []},
            {"exists": True, "path": str(source), "name": "source.mkv", "has_ptbr_audio": True, "ptbr_stream_index": 2, "streams": []},
        ]
        diagnose.return_value = {
            "category": "OFFSET_SUSPECTED",
            "offset_estimate": 1.25,
            "offset_confidence": 0.9,
            "diff": 1.25,
            "auto_offset_eligible": True,
            "auto_offset_reason": "offset-confidence-ok",
        }

        plan = build_preferred_audio_plan(str(target), str(source), "pt-BR-default", workspace)

    assert plan["ready"] is True
    assert plan["workflow_id"] == "preferred-audio-merge"
    assert plan["sync_review"]["status"] == "ok"
    assert plan["sync_review"]["suggested_offset_seconds"] == 1.25
    assert plan["ptbr_stream_index"] == 2


def test_run_preferred_audio_plan_uses_automatic_offset_when_safe(tmp_path: Path):
    workspace = ensure_workspace(tmp_path)
    target = workspace.input_dir / "target.mkv"
    source = workspace.input_dir / "source.mkv"
    output = workspace.output_dir / "target.preferred.mkv"
    target.write_bytes(b"target")
    source.write_bytes(b"source")
    plan = {
        "ready": True,
        "id": "plan-1",
        "workflow_id": "preferred-audio-merge",
        "target": {"path": str(target), "name": "target.mkv"},
        "source": {"path": str(source), "name": "source.mkv"},
        "output_path": str(output),
        "language_profile_id": "pt-BR-default",
        "ptbr_stream_index": 2,
        "sync_review": {
            "status": "ok",
            "suggested_offset_seconds": 1.25,
            "suggested_trim_start_seconds": 0.0,
            "suggested_trim_end_seconds": 0.0,
        },
        "manual_offset_seconds": None,
        "manual_trim_start_seconds": 0.0,
        "manual_trim_end_seconds": 0.0,
        "will_replace_original": False,
    }

    with patch("src.workflows.preferred_audio_merge.analyzer.get_ptbr_stream_index", return_value=2), \
        patch("src.workflows.preferred_audio_merge.merger.extract_audio", return_value=workspace.work_dir / "audio.eac3"), \
        patch("src.workflows.preferred_audio_merge.merger.mux_audio") as mux_audio, \
        patch("src.workflows.preferred_audio_merge.analyzer.validate_final_file", return_value={"valid": True, "reason": "OK"}):
        mux_audio.return_value = output
        result = run_preferred_audio_plan(plan, workspace)

    assert result["status"] == "SUCCESS"
    assert result["recipe_id"]
    mux_audio.assert_called_once()
    assert mux_audio.call_args.kwargs["audio_offset_seconds"] == 1.25
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
py -3 -m pytest -q tests/test_preferred_audio_merge_workflow.py
```

Expected:

```text
ModuleNotFoundError: No module named 'src.workflows'
```

- [ ] **Step 3: Create workflow package**

Create `src/workflows/__init__.py`:

```python
"""Local media workflows."""
```

- [ ] **Step 4: Implement preferred audio workflow**

Create `src/workflows/preferred_audio_merge.py`:

```python
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

import src.analyzer as analyzer
import src.merger as merger
from src.domain.media_workflow import JobStatus, Recipe, WorkflowJob
from src.storage.workflow_state import WorkflowState


WORKFLOW_ID = "preferred-audio-merge"
WORKFLOW_LABEL = "Adicionar audio a uma midia"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_output_path(target: Path, output_dir: Path) -> Path:
    candidate = output_dir / f"{target.stem}.preferred-audio.mkv"
    if not candidate.exists():
        return candidate
    for index in range(2, 100):
        numbered = output_dir / f"{target.stem}.preferred-audio-{index}.mkv"
        if not numbered.exists():
            return numbered
    raise RuntimeError("Nao foi possivel sugerir um nome de saida livre.")


def _sync_review_from_diagnosis(diagnosis: dict) -> dict:
    category = str(diagnosis.get("category") or "UNKNOWN_SYNC_FAILURE")
    auto_ok = bool(diagnosis.get("auto_offset_eligible"))
    status = "ok" if category == "SYNC_OK" or auto_ok else "attention"
    if diagnosis.get("terminal"):
        status = "blocked"
    return {
        "status": status,
        "confidence": float(diagnosis.get("offset_confidence") or 0.0),
        "suggested_offset_seconds": diagnosis.get("offset_estimate") if auto_ok else None,
        "suggested_trim_start_seconds": 0.0,
        "suggested_trim_end_seconds": 0.0,
        "reason": str(diagnosis.get("auto_offset_reason") or category),
        "duration_diff_seconds": float(diagnosis.get("diff") or 0.0),
        "diagnosis_category": category,
    }


def build_preferred_audio_plan(target_path: str, source_path: str, language_profile_id: str, workspace) -> dict:
    from src.web.ops import inspect_media_file

    target = inspect_media_file(target_path, workspace)
    source = inspect_media_file(source_path, workspace)
    problems: list[str] = []

    if not target.get("exists"):
        problems.append("Arquivo alvo nao encontrado.")
    if not source.get("exists"):
        problems.append("Arquivo fonte nao encontrado.")
    if target.get("exists") and source.get("exists") and target.get("path") == source.get("path"):
        problems.append("Alvo e fonte precisam ser arquivos diferentes.")
    if source.get("exists") and not source.get("has_ptbr_audio"):
        problems.append("A fonte precisa ter audio detectavel no perfil de idioma.")

    sync_review = {
        "status": "blocked",
        "confidence": 0.0,
        "suggested_offset_seconds": None,
        "suggested_trim_start_seconds": 0.0,
        "suggested_trim_end_seconds": 0.0,
        "reason": "inspection-blocked",
        "duration_diff_seconds": 0.0,
        "diagnosis_category": "NOT_EVALUATED",
    }
    if not problems:
        diagnosis = analyzer.diagnose_sync(Path(target["path"]), Path(source["path"]))
        sync_review = _sync_review_from_diagnosis(diagnosis)

    output_path = ""
    if target.get("exists"):
        output_path = str(_safe_output_path(Path(target["path"]), workspace.output_dir))

    return {
        "id": f"plan-{uuid.uuid4().hex}",
        "workflow_id": WORKFLOW_ID,
        "workflow_label": WORKFLOW_LABEL,
        "ready": not problems and sync_review["status"] != "blocked",
        "problems": problems,
        "target": target,
        "source": source,
        "output_path": output_path,
        "language_profile_id": language_profile_id or "pt-BR-default",
        "ptbr_stream_index": source.get("ptbr_stream_index"),
        "sync_review": sync_review,
        "manual_offset_seconds": None,
        "manual_trim_start_seconds": 0.0,
        "manual_trim_end_seconds": 0.0,
        "will_replace_original": False,
    }


def _selected_offset(plan: dict) -> float | None:
    manual = plan.get("manual_offset_seconds")
    if manual not in (None, ""):
        return float(manual)
    suggested = (plan.get("sync_review") or {}).get("suggested_offset_seconds")
    return float(suggested) if suggested not in (None, "") else None


def run_preferred_audio_plan(plan: dict, workspace) -> dict:
    if not plan.get("ready"):
        return {"status": "BLOCKED", "problems": plan.get("problems", [])}
    if plan.get("will_replace_original"):
        return {"status": "BLOCKED", "problems": ["Substituir original nao e permitido neste workflow."]}

    state = WorkflowState(workspace.root)
    job_id = f"job-{uuid.uuid4().hex}"
    recipe_id = f"recipe-{uuid.uuid4().hex}"
    now = _now()
    target = Path(plan["target"]["path"])
    source = Path(plan["source"]["path"])
    output_path = Path(plan["output_path"])
    stream_index = analyzer.get_ptbr_stream_index(source)
    if stream_index is None or int(stream_index) != int(plan.get("ptbr_stream_index", -1)):
        return {"status": "BLOCKED", "problems": ["A faixa de idioma mudou. Recrie o plano."]}

    state.upsert_job(
        WorkflowJob(
            id=job_id,
            workflow_id=WORKFLOW_ID,
            status=JobStatus.RUNNING,
            target_name=target.name,
            source_name=source.name,
            recipe_id=None,
            created_at=now,
            updated_at=now,
        )
    )

    audio_path = workspace.work_dir / f"{job_id}.preferred_audio.eac3"
    extracted = merger.extract_audio(source, int(stream_index), audio_path)
    merger.mux_audio(target, extracted, output_path, audio_offset_seconds=_selected_offset(plan))
    validation = analyzer.validate_final_file(output_path, target)
    status = "SUCCESS" if validation.get("valid") else "VALIDATION_FAILED"

    sync = plan.get("sync_review") or {}
    offset = _selected_offset(plan)
    sync_summary = "Sem offset automatico necessario" if offset in (None, 0.0) else f"Offset aplicado: {offset:.3f}s"
    report = {
        "job_id": job_id,
        "recipe_id": recipe_id,
        "workflow_id": WORKFLOW_ID,
        "status": status,
        "target_name": target.name,
        "source_name": source.name,
        "output_name": output_path.name,
        "language_profile_id": plan.get("language_profile_id"),
        "sync_review": sync,
        "sync_summary": sync_summary,
        "validation": validation,
        "will_replace_original": False,
    }
    report_path = workspace.reports_dir / f"{job_id}.report.json"
    report_path.write_text(__import__("json").dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    recipe = Recipe(
        id=recipe_id,
        job_id=job_id,
        workflow_id=WORKFLOW_ID,
        label=WORKFLOW_LABEL,
        target_name=target.name,
        source_name=source.name,
        output_name=output_path.name,
        language_profile_id=str(plan.get("language_profile_id") or "pt-BR-default"),
        sync_summary=sync_summary,
        validation_status=status,
        report_path=str(report_path),
        output_path=str(output_path),
        created_at=now,
    )
    state.upsert_recipe(recipe)
    state.upsert_job(
        WorkflowJob(
            id=job_id,
            workflow_id=WORKFLOW_ID,
            status=JobStatus.DONE if status == "SUCCESS" else JobStatus.FAILED,
            target_name=target.name,
            source_name=source.name,
            recipe_id=recipe_id,
            created_at=now,
            updated_at=_now(),
            last_error=None if status == "SUCCESS" else str(validation.get("reason") or status),
        )
    )
    return {
        "status": status,
        "job_id": job_id,
        "recipe_id": recipe_id,
        "output_path": str(output_path),
        "report_path": str(report_path),
        "validation": validation,
    }
```

- [ ] **Step 5: Run workflow tests**

Run:

```bash
py -3 -m pytest -q tests/test_preferred_audio_merge_workflow.py
```

Expected:

```text
2 passed
```

- [ ] **Step 6: Commit**

```bash
git add src/workflows/__init__.py src/workflows/preferred_audio_merge.py tests/test_preferred_audio_merge_workflow.py
git commit -m "feat: add preferred audio merge workflow"
```

---

### Task 5: Wire Web API To Workflows, Jobs, Recipes, And Profiles

**Files:**
- Modify: `src/web/ops.py`
- Modify: `src/web/server.py`
- Test: `tests/test_web_ops.py`
- Test: `tests/test_web_server.py`

- [ ] **Step 1: Add failing web ops tests**

Append to `tests/test_web_ops.py`:

```python
from src.web.ops import list_language_profiles, list_workflow_jobs, list_workflow_recipes


def test_web_ops_exposes_default_language_profile(tmp_path: Path):
    profiles = list_language_profiles(tmp_path)

    assert profiles[0]["id"] == "pt-BR-default"
    assert profiles[0]["label"] == "Portugues Brasil"


def test_web_ops_exposes_empty_jobs_and_recipes(tmp_path: Path):
    assert list_workflow_jobs(tmp_path) == []
    assert list_workflow_recipes(tmp_path) == []
```

- [ ] **Step 2: Add failing server tests**

Append to `tests/test_web_server.py`:

```python
def test_build_response_workflows_route(tmp_path: Path):
    status, headers, body = build_response("GET", "/api/workflows", b"", tmp_path)

    payload = json.loads(body.decode("utf-8"))

    assert status == 200
    assert payload["workflows"][0]["id"] == "preferred-audio-merge"
    assert payload["workflows"][0]["available"] is True


def test_build_response_jobs_recipes_and_profiles_routes(tmp_path: Path):
    for route in ("/api/jobs", "/api/recipes", "/api/language-profiles"):
        status, headers, body = build_response("GET", route, b"", tmp_path)
        assert status == 200
        assert headers["Content-Type"] == "application/json; charset=utf-8"
        assert json.loads(body.decode("utf-8"))
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```bash
py -3 -m pytest -q tests/test_web_ops.py::test_web_ops_exposes_default_language_profile tests/test_web_ops.py::test_web_ops_exposes_empty_jobs_and_recipes tests/test_web_server.py::test_build_response_workflows_route tests/test_web_server.py::test_build_response_jobs_recipes_and_profiles_routes
```

Expected:

```text
ImportError: cannot import name 'list_language_profiles'
```

- [ ] **Step 4: Add web ops wrappers**

Add this to `src/web/ops.py` near the other public operation helpers:

```python
from src.storage.workflow_state import WorkflowState
from src.workflows.preferred_audio_merge import build_preferred_audio_plan, run_preferred_audio_plan


def list_available_workflows() -> list[dict]:
    return [
        {
            "id": "preferred-audio-merge",
            "label": "Adicionar audio a uma midia",
            "description": "Use uma midia alvo e uma fonte com o idioma desejado para gerar um novo MKV sincronizado e validado.",
            "available": True,
        },
        {
            "id": "auto-language-download",
            "label": "Busca automatica por idioma",
            "description": "Visao futura: procurar, baixar e preparar midia pelo idioma preferido.",
            "available": False,
            "status": "planned",
        },
    ]


def list_language_profiles(root: Path | None = None) -> list[dict]:
    workspace = ensure_workspace(root)
    return WorkflowState(workspace.root).list_language_profiles()


def list_workflow_jobs(root: Path | None = None) -> list[dict]:
    workspace = ensure_workspace(root)
    return WorkflowState(workspace.root).list_jobs()


def list_workflow_recipes(root: Path | None = None) -> list[dict]:
    workspace = ensure_workspace(root)
    return WorkflowState(workspace.root).list_recipes()
```

If `src/web/ops.py` already imports names with the same identifiers, merge the imports instead of duplicating them.

- [ ] **Step 5: Add server routes**

Add these routes to `build_response()` in `src/web/server.py` before `/api/input-files`:

```python
    if method == "GET" and path == "/api/workflows":
        return _json_response({"workflows": ops.list_available_workflows()})
    if method == "GET" and path == "/api/jobs":
        return _json_response({"jobs": ops.list_workflow_jobs(root)})
    if method == "GET" and path == "/api/recipes":
        return _json_response({"recipes": ops.list_workflow_recipes(root)})
    if method == "GET" and path == "/api/language-profiles":
        return _json_response({"profiles": ops.list_language_profiles(root)})
```

Replace the existing `/api/manual-plan` route body with:

```python
        plan = ops.build_preferred_audio_plan(
            str(payload.get("target_path") or ""),
            str(payload.get("source_path") or ""),
            str(payload.get("language_profile_id") or "pt-BR-default"),
            workspace,
        )
```

Replace the existing `/api/manual-run` execution call with:

```python
            return _json_response(ops.run_preferred_audio_plan(plan, workspace))
```

- [ ] **Step 6: Run web tests**

Run:

```bash
py -3 -m pytest -q tests/test_web_ops.py tests/test_web_server.py
```

Expected:

```text
all tests pass
```

- [ ] **Step 7: Commit**

```bash
git add src/web/ops.py src/web/server.py tests/test_web_ops.py tests/test_web_server.py
git commit -m "feat: expose local workflow hub api"
```

---

### Task 6: Reshape The Web UI Into A Hub With One Real Workflow

**Files:**
- Modify: `src/web/static/index.html`
- Modify: `src/web/static/app.js`
- Modify: `src/web/static/styles.css`
- Test: `tests/test_web_static.py`

- [ ] **Step 1: Add failing static UI vocabulary tests**

Create `tests/test_web_static.py`:

```python
from pathlib import Path


STATIC = Path("src/web/static")


def test_hub_navigation_labels_are_present():
    html = (STATIC / "index.html").read_text(encoding="utf-8")

    for label in ("Inicio", "Workflows", "Fila", "Arquivos locais", "Receitas", "Perfis", "Ferramentas", "Configuracoes"):
        assert label in html


def test_ui_does_not_present_future_integrations_as_active_features():
    html = (STATIC / "index.html").read_text(encoding="utf-8")

    assert "Busca automatica, qBittorrent e indexers fazem parte da visao futura" in html
    assert 'data-screen="indexers"' not in html
    assert 'data-screen="trackers"' not in html
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
py -3 -m pytest -q tests/test_web_static.py
```

Expected:

```text
FAILED ... assert 'Inicio' in html
```

- [ ] **Step 3: Update navigation in `index.html`**

In `src/web/static/index.html`, replace the current nav buttons with:

```html
<button class="nav-item active" type="button" data-screen="home">Inicio</button>
<button class="nav-item" type="button" data-screen="workflows">Workflows</button>
<button class="nav-item" type="button" data-screen="queue">Fila</button>
<button class="nav-item" type="button" data-screen="files">Arquivos locais</button>
<button class="nav-item" type="button" data-screen="recipes">Receitas</button>
<button class="nav-item" type="button" data-screen="profiles">Perfis</button>
<button class="nav-item" type="button" data-screen="tools">Ferramentas</button>
<button class="nav-item" type="button" data-screen="settings">Configuracoes</button>
```

Rename the current merge screen section to:

```html
<section id="screen-home" class="screen active" aria-labelledby="home-title">
```

Use this header inside it:

```html
<header class="screen-header">
  <div>
    <p class="kicker">Hub local de midia</p>
    <h1 id="home-title">Oficina local para workflows de midia</h1>
    <p>Esta versao inaugura o hub com um workflow real: adicionar, sincronizar e muxar audio em uma midia local sem substituir originais.</p>
  </div>
  <button id="refresh-status" type="button" class="secondary" data-testid="refresh-status">Verificar</button>
</header>
```

Add this non-clickable future vision block to the Workflows screen:

```html
<section id="screen-workflows" class="screen" aria-labelledby="workflows-title">
  <header class="screen-header">
    <div>
      <p class="kicker">Workflows</p>
      <h1 id="workflows-title">Fluxos de trabalho</h1>
      <p>Escolha o que o hub deve fazer com seus arquivos locais.</p>
    </div>
  </header>
  <div id="workflow-list" class="workflow-list"></div>
  <section class="panel vision-panel">
    <h2>Visao do hub</h2>
    <p>Busca automatica, qBittorrent e indexers fazem parte da visao futura do hub, mas nao sao configuraveis nesta versao.</p>
  </section>
</section>
```

Add empty sections for queue, recipes, profiles, and tools with these ids:

```html
<section id="screen-queue" class="screen" aria-labelledby="queue-title">
  <header class="screen-header"><div><p class="kicker">Fila</p><h1 id="queue-title">Tarefas</h1><p>Historico simples das execucoes criadas pela interface web.</p></div></header>
  <div id="job-list" class="entity-list"></div>
</section>

<section id="screen-recipes" class="screen" aria-labelledby="recipes-title">
  <header class="screen-header"><div><p class="kicker">Receitas</p><h1 id="recipes-title">Receitas e relatorios</h1><p>Entenda o que o app fez sem abrir JSON.</p></div></header>
  <div id="recipe-list" class="entity-list"></div>
</section>

<section id="screen-profiles" class="screen" aria-labelledby="profiles-title">
  <header class="screen-header"><div><p class="kicker">Perfis</p><h1 id="profiles-title">Perfil de idioma</h1><p>Preferencias usadas pelos workflows de idioma.</p></div></header>
  <div id="profile-list" class="entity-list"></div>
</section>

<section id="screen-tools" class="screen" aria-labelledby="tools-title">
  <header class="screen-header"><div><p class="kicker">Ferramentas</p><h1 id="tools-title">Suporte local</h1><p>Diagnostico, dependencias, pastas e logs recentes.</p></div></header>
  <div class="settings-grid">
    <button id="check-dependencies" type="button" class="secondary">Verificar dependencias</button>
    <button type="button" data-open-location="input">Abrir input</button>
    <button type="button" data-open-location="output">Abrir output</button>
    <button type="button" data-open-location="reports">Abrir reports</button>
  </div>
</section>
```

- [ ] **Step 4: Update app.js to load new lists**

Add these functions to `src/web/static/app.js`:

```javascript
async function loadWorkflows() {
  const payload = await api("/api/workflows");
  const list = node("workflow-list");
  if (!list) return;
  list.innerHTML = "";
  (payload.workflows || []).forEach((workflow) => {
    const item = document.createElement("article");
    item.className = `panel workflow-card ${workflow.available ? "" : "disabled-card"}`;
    item.innerHTML = `
      <h2>${escapeHtml(workflow.label)}</h2>
      <p>${escapeHtml(workflow.description || "")}</p>
      <span>${workflow.available ? "Disponivel agora" : "Planejado"}</span>
    `;
    list.appendChild(item);
  });
}

async function loadJobs() {
  const payload = await api("/api/jobs");
  renderEntityList("job-list", payload.jobs || [], "Nenhuma tarefa criada nesta sessao.");
}

async function loadRecipes() {
  const payload = await api("/api/recipes");
  renderEntityList("recipe-list", payload.recipes || [], "Nenhuma receita salva ainda.");
}

async function loadProfiles() {
  const payload = await api("/api/language-profiles");
  renderEntityList("profile-list", payload.profiles || [], "Nenhum perfil encontrado.");
}

function renderEntityList(id, items, emptyText) {
  const list = node(id);
  if (!list) return;
  list.innerHTML = "";
  if (!items.length) {
    list.innerHTML = `<div class="friendly-output">${escapeHtml(emptyText)}</div>`;
    return;
  }
  items.forEach((item) => {
    const row = document.createElement("article");
    row.className = "entity-row";
    row.innerHTML = `
      <strong>${escapeHtml(item.label || item.id || item.workflow_id || "item")}</strong>
      <small>${escapeHtml(item.status || item.preferred_audio_language || item.validation_status || "")}</small>
    `;
    list.appendChild(row);
  });
}
```

Call these near the existing startup calls:

```javascript
loadWorkflows();
loadJobs();
loadRecipes();
loadProfiles();
```

After `renderRunResult(result);` in `runPlan()`, add:

```javascript
await loadJobs();
await loadRecipes();
```

- [ ] **Step 5: Add CSS for hub lists**

Append to `src/web/static/styles.css`:

```css
.workflow-list,
.entity-list {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 14px;
}

.workflow-card span,
.entity-row small {
  color: var(--muted);
}

.disabled-card {
  opacity: 0.72;
}

.entity-row {
  display: grid;
  gap: 6px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--surface);
  padding: 13px;
}

.vision-panel {
  margin-top: 14px;
}
```

- [ ] **Step 6: Run static and web tests**

Run:

```bash
py -3 -m pytest -q tests/test_web_static.py tests/test_web_server.py tests/test_web_ops.py
```

Expected:

```text
all tests pass
```

- [ ] **Step 7: Commit**

```bash
git add src/web/static/index.html src/web/static/app.js src/web/static/styles.css tests/test_web_static.py
git commit -m "feat: reshape web mode into media workflow hub"
```

---

### Task 7: Harden Windows Launcher For Non-Technical Startup

**Files:**
- Modify: `START_PTBRMERGER.bat`
- Modify: `scripts/start-ptbrmerger-hidden.ps1`
- Test: `tests/test_launcher_scripts.py`

- [ ] **Step 1: Add failing launcher script tests**

Create `tests/test_launcher_scripts.py`:

```python
from pathlib import Path


def test_batch_launcher_delegates_to_hidden_powershell_script():
    content = Path("START_PTBRMERGER.bat").read_text(encoding="utf-8", errors="replace")

    assert "scripts\\start-ptbrmerger-hidden.ps1" in content
    assert "ExecutionPolicy Bypass" in content


def test_hidden_launcher_prefers_py_launcher_and_mentions_store_alias():
    content = Path("scripts/start-ptbrmerger-hidden.ps1").read_text(encoding="utf-8", errors="replace")

    assert 'Test-Command "py.exe"' in content
    assert '@("-3") + $pythonArgs' in content
    assert "Microsoft Store" in content
    assert "127.0.0.1" in content
    assert "8787" in content
```

- [ ] **Step 2: Run tests**

Run:

```bash
py -3 -m pytest -q tests/test_launcher_scripts.py
```

Expected:

```text
2 passed
```

If these tests already pass because the launcher has been manually hardened, keep the tests and continue to the commit.

- [ ] **Step 3: If tests fail, update `START_PTBRMERGER.bat`**

Use this content:

```bat
@echo off
cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0scripts\start-ptbrmerger-hidden.ps1"
exit /b %errorlevel%
```

- [ ] **Step 4: If tests fail, update `scripts/start-ptbrmerger-hidden.ps1` Python selection**

Ensure this block exists:

```powershell
$pythonExe = $null
$pythonArgs = @("-m", "src.web.server")
$venvPython = Join-Path $root ".venv\Scripts\python.exe"

if (Test-Path $venvPython) {
    $pythonExe = $venvPython
} elseif (Test-Command "py.exe") {
    $pythonExe = "py.exe"
    $pythonArgs = @("-3") + $pythonArgs
} elseif (Test-Command "python.exe") {
    $pythonExe = "python.exe"
}

if (-not $pythonExe) {
    Write-LaunchError "Python nao encontrado. Instale Python 3.11+ ou desative o alias da Microsoft Store para python.exe."
    exit 1
}
```

- [ ] **Step 5: Run launcher tests**

Run:

```bash
py -3 -m pytest -q tests/test_launcher_scripts.py
```

Expected:

```text
2 passed
```

- [ ] **Step 6: Commit**

```bash
git add START_PTBRMERGER.bat scripts/start-ptbrmerger-hidden.ps1 tests/test_launcher_scripts.py
git commit -m "test: lock windows launcher recovery behavior"
```

---

### Task 8: Add Simple Support Package Endpoint

**Files:**
- Modify: `src/web/ops.py`
- Modify: `src/web/server.py`
- Modify: `src/web/static/app.js`
- Test: `tests/test_web_ops.py`
- Test: `tests/test_web_server.py`

- [ ] **Step 1: Add failing support package tests**

Append to `tests/test_web_ops.py`:

```python
from src.web.ops import build_support_package


def test_build_support_package_writes_safe_json_without_secrets(tmp_path: Path):
    workspace = ensure_workspace(tmp_path)
    (workspace.logs_dir / "app.log").write_text("line 1\nline 2\n", encoding="utf-8")

    payload = build_support_package(workspace)

    assert payload["status"] == "CREATED"
    assert payload["path"].endswith(".support.json")
    content = Path(payload["path"]).read_text(encoding="utf-8")
    assert "line 1" in content
    assert "api_key" not in content.lower()
    assert "password" not in content.lower()
```

Append to `tests/test_web_server.py`:

```python
def test_build_response_support_package_route(tmp_path: Path):
    status, headers, body = build_response("POST", "/api/support-package", b"{}", tmp_path)

    payload = json.loads(body.decode("utf-8"))

    assert status == 200
    assert payload["status"] == "CREATED"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
py -3 -m pytest -q tests/test_web_ops.py::test_build_support_package_writes_safe_json_without_secrets tests/test_web_server.py::test_build_response_support_package_route
```

Expected:

```text
ImportError: cannot import name 'build_support_package'
```

- [ ] **Step 3: Implement support package helper**

Add to `src/web/ops.py`:

```python
def build_support_package(workspace: LocalWorkspace) -> dict:
    created_at = datetime.now(timezone.utc).isoformat()
    logs = []
    for path in sorted(workspace.logs_dir.glob("*.log"))[:5]:
        try:
            logs.append({"name": path.name, "tail": path.read_text(encoding="utf-8", errors="replace").splitlines()[-80:]})
        except OSError:
            logs.append({"name": path.name, "tail": ["Nao foi possivel ler este log."]})
    package = {
        "created_at": created_at,
        "workspace": {
            "input_dir": "input/",
            "output_dir": "output/",
            "reports_dir": "reports/",
            "recipes_dir": "recipes/",
        },
        "jobs": list_workflow_jobs(workspace.root),
        "recipes": list_workflow_recipes(workspace.root),
        "language_profiles": list_language_profiles(workspace.root),
        "logs": logs,
        "privacy": {
            "contains_media": False,
            "contains_credentials": False,
            "contains_tracker_urls": False,
            "contains_api_keys": False,
        },
    }
    output_path = workspace.reports_dir / f"support-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.support.json"
    _write_json(output_path, package)
    return {"status": "CREATED", "path": str(output_path)}
```

- [ ] **Step 4: Add server route**

Add to `build_response()` in `src/web/server.py`:

```python
    if method == "POST" and path == "/api/support-package":
        return _json_response(ops.build_support_package(workspace))
```

- [ ] **Step 5: Add UI button call**

Add a button in the Tools screen:

```html
<button id="build-support-package" type="button" class="secondary">Gerar pacote de suporte</button>
```

Add to `src/web/static/app.js`:

```javascript
async function buildSupportPackage() {
  const result = await api("/api/support-package", { method: "POST", body: "{}" });
  renderRunResult(result);
}

node("build-support-package").addEventListener("click", buildSupportPackage);
```

- [ ] **Step 6: Run support package tests**

Run:

```bash
py -3 -m pytest -q tests/test_web_ops.py::test_build_support_package_writes_safe_json_without_secrets tests/test_web_server.py::test_build_response_support_package_route
```

Expected:

```text
2 passed
```

- [ ] **Step 7: Commit**

```bash
git add src/web/ops.py src/web/server.py src/web/static/index.html src/web/static/app.js tests/test_web_ops.py tests/test_web_server.py
git commit -m "feat: add local support package export"
```

---

### Task 9: Align README And Planning Around The Hub Vision

**Files:**
- Modify: `README.md`
- Modify: `.planning/PROJECT.md`
- Modify: `.planning/ROADMAP.md`

- [ ] **Step 1: Update README opening**

Replace the first paragraph after `# PTBRMerger` in `README.md` with:

```markdown
PTBRMerger is evolving into a local media workflow hub. Today, its strongest complete workflow adds and synchronizes preferred-language audio into local MKV files and the existing Radarr/qBittorrent automation. The long-term direction is broader: local workflows for language preference, mux/remux, subtitles, metadata, organization, download-client integration and eventually automatic source discovery.

The current product stays local-first and safety-first:

- local web UI bound to `127.0.0.1`;
- no cloud account;
- no tracker/indexer management in v0.5;
- no original-file replacement in the local web workflow;
- recipes and reports for every local output;
- legacy Radarr/qBittorrent automation preserved but not expanded in this phase.
```

- [ ] **Step 2: Add v0.5 section to README**

Add this before `## Current Flow`:

```markdown
## Product Direction: Local Media Workflow Hub

The app should not stay limited to one PT-BR merge use case. The local web UI is becoming the primary product surface for media workflows.

The first complete hub workflow is:

```text
target MKV + source MKV -> inspect -> plan -> sync review -> mux -> validate -> recipe/report
```

Future hub areas include preferred-language download rules, qBittorrent integration, indexers, folder monitoring, subtitles, remux, rename and metadata workflows. Those are vision items, not v0.5 promises.
```

- [ ] **Step 3: Update `.planning/PROJECT.md`**

Replace the `## What This Is` paragraph with:

```markdown
PTBRMerger is becoming a Windows-first local media workflow hub. Its current proven workflows focus on preferred-language audio for MKV files and a legacy Radarr/qBittorrent automation pipeline, but the product direction is broader: safe local workflows for inspecting, synchronizing, muxing, remuxing, subtitling, organizing and eventually sourcing media by user preference.
```

Add this decision to the Key Decisions table:

```markdown
| Treat PT-BR merge as the first workflow, not the final product identity | The user wants a larger local media automation hub; the app should use workflows, profiles, jobs and recipes as product primitives while keeping v0.5 scoped | Pending |
```

- [ ] **Step 4: Update `.planning/ROADMAP.md`**

Add under active/next milestones:

```markdown
- 🚧 **v0.5 Local Media Workflow Hub** - first real hub workflow, jobs, recipes, profiles and sync review
```

Add a v0.5 section:

```markdown
## Next Milestone: v0.5 Local Media Workflow Hub

Goal: make the web UI the primary local hub surface while shipping one real workflow: add and automatically synchronize preferred-language audio into a local MKV with safe output, recipes, reports and a simple execution history.

Out of scope: indexers, trackers, automatic source search, qBittorrent-first replacement flow, folder watcher, plugin system, cloud, multi-user support, full trigger rewrite.
```

- [ ] **Step 5: Run docs grep**

Run:

```bash
Select-String -Path README.md,.planning/PROJECT.md,.planning/ROADMAP.md -Pattern "Local Media Workflow Hub|first workflow|indexers|qBittorrent"
```

Expected:

```text
At least one match in each file.
```

- [ ] **Step 6: Commit**

```bash
git add README.md .planning/PROJECT.md .planning/ROADMAP.md
git commit -m "docs: frame v05 as local media workflow hub"
```

---

### Task 10: Validate v0.5 End To End

**Files:**
- No planned source edits. Fix only failures found during validation.

- [ ] **Step 1: Run focused new tests**

Run:

```bash
py -3 -m pytest -q tests/test_domain_media_workflow.py tests/test_storage_json_store.py tests/test_workflow_state.py tests/test_preferred_audio_merge_workflow.py tests/test_web_static.py tests/test_launcher_scripts.py
```

Expected:

```text
all tests pass
```

- [ ] **Step 2: Run existing web and tool tests**

Run:

```bash
py -3 -m pytest -q tests/test_web_ops.py tests/test_web_server.py tests/test_tools.py
```

Expected:

```text
all tests pass
```

- [ ] **Step 3: Run full test suite**

Run:

```bash
py -3 -m pytest -q
```

Expected:

```text
all tests pass
```

- [ ] **Step 4: Run compile check**

Run:

```bash
py -3 -m compileall src tests
```

Expected:

```text
No syntax errors.
```

- [ ] **Step 5: Start local server**

Run:

```bash
py -3 -m src.web.server
```

Expected:

```text
PTBRMerger local web mode: http://127.0.0.1:8787
```

- [ ] **Step 6: Browser validation**

Use Browser Use to open:

```text
http://127.0.0.1:8787
```

Validate:

- Inicio loads and explains the hub as local media workflows.
- Workflows shows `Adicionar audio a uma midia` as available.
- Planned future items are visible only as planned, not clickable active features.
- Fila loads empty state.
- Receitas loads empty state.
- Perfis shows `Portugues Brasil`.
- Ferramentas can check dependencies.
- Configuracoes still exposes FFmpeg/FFprobe setup.
- Existing file selection still works.
- Creating a plan shows sync review.
- Running a plan writes output only under `output/`.
- Result creates job and recipe entries.
- Console has no runtime errors.

- [ ] **Step 7: Fix and rerun targeted tests if needed**

If validation finds a bug, fix the smallest affected surface and rerun:

```bash
py -3 -m pytest -q <affected-test-file>
py -3 -m compileall src tests
```

- [ ] **Step 8: Commit final fixes**

```bash
git add <fixed-files>
git commit -m "fix: harden local media workflow hub validation"
```

---

## Self-Review

**Spec coverage:** This plan covers the user's decisions: web as primary UI, automatic sync as focus, JSON kept but hidden behind user-safe stores, legacy Radarr/qBittorrent frozen, and hub vision visible without implementing indexers/search/download automation in v0.5.

**Placeholder scan:** The plan does not use TBD/TODO/fill-later language. Future items are explicitly marked out of scope or planned-only UI text.

**Type consistency:** The plan consistently uses `WorkflowJob`, `Recipe`, `LanguageProfile`, `OperationPlan`, `SyncReview`, `WorkflowState`, and `preferred-audio-merge`.

**Risk controls:**

- Original files are never replaced by the local web workflow.
- JSON state is atomic and backed up.
- Future integrations are not shown as active features.
- Sync manual controls exist only as fallback; automatic sync is the main path.
- Legacy `trigger.py` remains stable.
- Launcher uses `py -3` before `python.exe` to avoid the Microsoft Store alias trap.

Plan complete and saved to `docs/superpowers/plans/2026-04-27-local-media-workflow-hub-v05.md`. Two execution options:

1. **Subagent-Driven (recommended)** - dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** - execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
