# Post-Format Recovery Web Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a minimal local web recovery mode so PTBRMerger can be used after a PC format without reconfiguring Radarr, qBittorrent, Bazarr, or Discord.

**Architecture:** Add a stdlib-only local HTTP server bound to `127.0.0.1:8787`, with static HTML/CSS/JS and a small allowlisted API layer. The web layer calls focused local operation functions that reuse existing analyzer/merger/preflight behavior, always writes generated files under local workspace folders, and never replaces the original movie by default.

**Tech Stack:** Python 3.11 stdlib `http.server`, existing `src.analyzer`, existing `src.merger`, existing `src.tools.preflight`, plain HTML/CSS/JS, pytest.

---

## Final Product Decision

The primary recovery UX for v0.4.5 is **web local**, not CLI-first.

The user starts it with:

```bat
START_PTBRMERGER.bat
```

The batch file launches:

```bash
python -m src.web.server
```

Then opens:

```text
http://127.0.0.1:8787
```

This is not a dashboard, desktop app, cloud service, tracker, or new download automation. It is a local, minimal recovery surface for:

- seeing what works on the freshly formatted PC;
- using the existing pipeline manually with two local files;
- generating a safe output file under `output/`;
- producing a report and future-compatible local recipe.

## File Structure

Create:

- `START_PTBRMERGER.bat`
  - Windows launcher. Starts the local server and opens the browser.

- `src/web/__init__.py`
  - Marks the web module package.

- `src/web/ops.py`
  - Pure local operations for workspace setup, status, input file listing, file inspection, manual plan creation, manual run execution, report creation, and recipe creation.

- `src/web/server.py`
  - Stdlib HTTP server. Routes only allowlisted endpoints. Binds to `127.0.0.1` only.

- `src/web/static/index.html`
  - One-screen local recovery UI.

- `src/web/static/styles.css`
  - Focused local product styling, not a dashboard grid.

- `src/web/static/app.js`
  - Browser interactions against the local API.

- `tests/test_web_ops.py`
  - Unit tests for local operation functions.

- `tests/test_web_server.py`
  - Unit tests for API routing and safety behavior without launching a real browser.

Modify:

- `README.md`
  - Add a short "Retomada pos-formatacao" path.

- `.planning/ROADMAP.md`
  - Rename v0.4.5 from Guided Operations to Post-Format Recovery Web Mode.

- `.planning/PROJECT.md`
  - Record that web local is the primary recovery UX; CLI remains technical support only.

Do not modify:

- `src/trigger.py` in this milestone unless a later task proves a small shared helper is necessary.
- Radarr/qBittorrent/Bazarr clients.
- Existing destructive replacement behavior in `src.merger.validate_and_replace`.

---

### Task 1: Add Local Web Ops Skeleton

**Files:**
- Create: `src/web/__init__.py`
- Create: `src/web/ops.py`
- Test: `tests/test_web_ops.py`

- [ ] **Step 1: Write failing tests for workspace creation and safe path classification**

Add this to `tests/test_web_ops.py`:

```python
from pathlib import Path

from src.web.ops import LocalWorkspace, ensure_workspace, resolve_user_path


def test_ensure_workspace_creates_expected_directories(tmp_path: Path):
    workspace = ensure_workspace(tmp_path)

    assert workspace.root == tmp_path
    assert workspace.input_dir == tmp_path / "input"
    assert workspace.output_dir == tmp_path / "output"
    assert workspace.work_dir == tmp_path / "workdir"
    assert workspace.reports_dir == tmp_path / "reports"
    assert workspace.recipes_dir == tmp_path / "recipes"
    assert workspace.logs_dir == tmp_path / "logs"
    for path in (
        workspace.input_dir,
        workspace.output_dir,
        workspace.work_dir,
        workspace.reports_dir,
        workspace.recipes_dir,
        workspace.logs_dir,
    ):
        assert path.exists()
        assert path.is_dir()


def test_resolve_user_path_accepts_input_file_and_rejects_missing_path(tmp_path: Path):
    workspace = ensure_workspace(tmp_path)
    movie = workspace.input_dir / "movie.mkv"
    movie.write_bytes(b"fake")

    resolved = resolve_user_path(str(movie), workspace)

    assert resolved == movie.resolve()
    missing = resolve_user_path(str(workspace.input_dir / "missing.mkv"), workspace)
    assert missing is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest -q tests/test_web_ops.py
```

Expected:

```text
ModuleNotFoundError: No module named 'src.web'
```

- [ ] **Step 3: Create the web package**

Create `src/web/__init__.py`:

```python
"""Local web recovery mode for PTBRMerger."""
```

- [ ] **Step 4: Implement minimal workspace helpers**

Create `src/web/ops.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LocalWorkspace:
    root: Path
    input_dir: Path
    output_dir: Path
    work_dir: Path
    reports_dir: Path
    recipes_dir: Path
    logs_dir: Path


def ensure_workspace(root: Path | None = None) -> LocalWorkspace:
    base = (root or Path.cwd()).resolve()
    workspace = LocalWorkspace(
        root=base,
        input_dir=base / "input",
        output_dir=base / "output",
        work_dir=base / "workdir",
        reports_dir=base / "reports",
        recipes_dir=base / "recipes",
        logs_dir=base / "logs",
    )
    for path in (
        workspace.input_dir,
        workspace.output_dir,
        workspace.work_dir,
        workspace.reports_dir,
        workspace.recipes_dir,
        workspace.logs_dir,
    ):
        path.mkdir(parents=True, exist_ok=True)
    return workspace


def resolve_user_path(raw_path: str, workspace: LocalWorkspace) -> Path | None:
    value = str(raw_path or "").strip().strip('"')
    if not value:
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = workspace.root / path
    resolved = path.resolve()
    if not resolved.exists() or not resolved.is_file():
        return None
    return resolved
```

- [ ] **Step 5: Run tests**

Run:

```bash
pytest -q tests/test_web_ops.py
```

Expected:

```text
2 passed
```

- [ ] **Step 6: Commit**

```bash
git add src/web/__init__.py src/web/ops.py tests/test_web_ops.py
git commit -m "feat: add local web workspace helpers"
```

---

### Task 2: Add Human Status Model For Fresh PCs

**Files:**
- Modify: `src/web/ops.py`
- Test: `tests/test_web_ops.py`

- [ ] **Step 1: Write failing tests for status normalization**

Append to `tests/test_web_ops.py`:

```python
from unittest.mock import patch

from src.web.ops import build_local_status


def test_build_local_status_marks_radarr_and_qbit_as_optional(tmp_path: Path):
    preflight = {
        "status": "BLOCKER",
        "checks": [
            {"name": "ffmpeg", "status": "OK", "message": "available"},
            {"name": "ffprobe", "status": "OK", "message": "available"},
            {"name": "radarr", "status": "BLOCKER", "message": "unreachable"},
            {"name": "qbittorrent", "status": "BLOCKER", "message": "login-failed"},
            {"name": "bazarr", "status": "WARN", "message": "disabled-or-missing-config"},
            {"name": "discord", "status": "WARN", "message": "disabled"},
        ],
    }

    with patch("src.web.ops.run_preflight", return_value=preflight):
        status = build_local_status(tmp_path)

    assert status["mode"] == "manual-recovery"
    assert status["manual_ready"] is True
    assert status["automation_ready"] is False
    assert status["summary"] == "Modo manual disponivel. Automacao externa incompleta."
    assert status["checks"]["radarr"]["required_for_manual"] is False
    assert status["checks"]["qbittorrent"]["required_for_manual"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest -q tests/test_web_ops.py::test_build_local_status_marks_radarr_and_qbit_as_optional -v
```

Expected:

```text
ImportError: cannot import name 'build_local_status'
```

- [ ] **Step 3: Implement status normalization**

Add to `src/web/ops.py`:

```python
from src.tools.preflight import run_preflight


MANUAL_REQUIRED_CHECKS = {"ffmpeg", "ffprobe"}
AUTOMATION_REQUIRED_CHECKS = {"radarr", "qbittorrent"}


def build_local_status(root: Path | None = None) -> dict:
    workspace = ensure_workspace(root)
    report = run_preflight(base_dir=workspace.root)
    checks = {}
    for item in report.get("checks", []):
        name = str(item.get("name") or "")
        checks[name] = {
            **item,
            "required_for_manual": name in MANUAL_REQUIRED_CHECKS,
            "required_for_automation": name in AUTOMATION_REQUIRED_CHECKS,
        }

    manual_ready = all(checks.get(name, {}).get("status") == "OK" for name in MANUAL_REQUIRED_CHECKS)
    automation_ready = all(checks.get(name, {}).get("status") == "OK" for name in AUTOMATION_REQUIRED_CHECKS)
    if manual_ready and not automation_ready:
        summary = "Modo manual disponivel. Automacao externa incompleta."
    elif manual_ready and automation_ready:
        summary = "Modo manual e automacao externa disponiveis."
    else:
        summary = "Modo manual bloqueado. Corrija FFmpeg/FFprobe primeiro."

    return {
        "mode": "manual-recovery",
        "manual_ready": manual_ready,
        "automation_ready": automation_ready,
        "summary": summary,
        "workspace": {
            "root": str(workspace.root),
            "input_dir": str(workspace.input_dir),
            "output_dir": str(workspace.output_dir),
            "reports_dir": str(workspace.reports_dir),
            "recipes_dir": str(workspace.recipes_dir),
        },
        "checks": checks,
    }
```

- [ ] **Step 4: Run focused tests**

Run:

```bash
pytest -q tests/test_web_ops.py::test_build_local_status_marks_radarr_and_qbit_as_optional -v
```

Expected:

```text
1 passed
```

- [ ] **Step 5: Commit**

```bash
git add src/web/ops.py tests/test_web_ops.py
git commit -m "feat: expose local recovery status"
```

---

### Task 3: Add Input File Listing And Inspection

**Files:**
- Modify: `src/web/ops.py`
- Test: `tests/test_web_ops.py`

- [ ] **Step 1: Write failing tests for input listing and inspect payload**

Append to `tests/test_web_ops.py`:

```python
from unittest.mock import patch

from src.web.ops import inspect_media_file, list_input_files


def test_list_input_files_only_returns_mkv_files(tmp_path: Path):
    workspace = ensure_workspace(tmp_path)
    (workspace.input_dir / "target.mkv").write_bytes(b"a")
    (workspace.input_dir / "source.MKV").write_bytes(b"b")
    (workspace.input_dir / "notes.txt").write_text("ignore", encoding="utf-8")

    files = list_input_files(workspace)

    assert [item["name"] for item in files] == ["source.MKV", "target.mkv"]


def test_inspect_media_file_returns_stream_summary(tmp_path: Path):
    workspace = ensure_workspace(tmp_path)
    movie = workspace.input_dir / "source.mkv"
    movie.write_bytes(b"fake")
    probe = {
        "format": {"duration": "120.5"},
        "streams": [
            {"index": 0, "codec_type": "video", "codec_name": "hevc", "tags": {}},
            {"index": 1, "codec_type": "audio", "codec_name": "eac3", "tags": {"language": "por", "title": "PT-BR"}},
        ],
    }

    with patch("src.web.ops.analyzer._probe_file", return_value=probe):
        payload = inspect_media_file(str(movie), workspace)

    assert payload["exists"] is True
    assert payload["duration_seconds"] == 120.5
    assert payload["has_ptbr_audio"] is True
    assert payload["ptbr_stream_index"] == 1
    assert payload["streams"][1]["language"] == "por"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest -q tests/test_web_ops.py::test_list_input_files_only_returns_mkv_files tests/test_web_ops.py::test_inspect_media_file_returns_stream_summary -v
```

Expected:

```text
ImportError: cannot import name 'inspect_media_file'
```

- [ ] **Step 3: Implement listing and inspection**

Add to `src/web/ops.py`:

```python
import src.analyzer as analyzer


def list_input_files(workspace: LocalWorkspace) -> list[dict]:
    files = []
    for path in sorted(workspace.input_dir.glob("*"), key=lambda item: item.name.lower()):
        if path.is_file() and path.suffix.lower() == ".mkv":
            files.append(
                {
                    "name": path.name,
                    "path": str(path),
                    "size_bytes": path.stat().st_size,
                }
            )
    return files


def _stream_summary(stream: dict) -> dict:
    tags = stream.get("tags", {}) or {}
    return {
        "index": stream.get("index"),
        "type": stream.get("codec_type"),
        "codec": stream.get("codec_name"),
        "language": tags.get("language", ""),
        "title": tags.get("title", ""),
    }


def inspect_media_file(raw_path: str, workspace: LocalWorkspace) -> dict:
    path = resolve_user_path(raw_path, workspace)
    if path is None:
        return {"exists": False, "error": "Arquivo nao encontrado."}

    probe = analyzer._probe_file(path)
    streams = [_stream_summary(stream) for stream in probe.get("streams", [])]
    duration_raw = probe.get("format", {}).get("duration", "0")
    try:
        duration = float(duration_raw)
    except (TypeError, ValueError):
        duration = 0.0
    ptbr_stream_index = analyzer.get_ptbr_stream_index(path)
    return {
        "exists": True,
        "path": str(path),
        "name": path.name,
        "duration_seconds": duration,
        "has_ptbr_audio": ptbr_stream_index is not None,
        "ptbr_stream_index": ptbr_stream_index,
        "streams": streams,
    }
```

- [ ] **Step 4: Run focused tests**

Run:

```bash
pytest -q tests/test_web_ops.py::test_list_input_files_only_returns_mkv_files tests/test_web_ops.py::test_inspect_media_file_returns_stream_summary -v
```

Expected:

```text
2 passed
```

- [ ] **Step 5: Commit**

```bash
git add src/web/ops.py tests/test_web_ops.py
git commit -m "feat: inspect local media for web recovery"
```

---

### Task 4: Add Manual Recovery Plan

**Files:**
- Modify: `src/web/ops.py`
- Test: `tests/test_web_ops.py`

- [ ] **Step 1: Write failing tests for manual plan creation**

Append to `tests/test_web_ops.py`:

```python
from src.web.ops import build_manual_plan


def test_build_manual_plan_requires_source_with_ptbr_audio(tmp_path: Path):
    workspace = ensure_workspace(tmp_path)
    target = workspace.input_dir / "target.mkv"
    source = workspace.input_dir / "source.mkv"
    target.write_bytes(b"target")
    source.write_bytes(b"source")

    with patch("src.web.ops.inspect_media_file") as inspect:
        inspect.side_effect = [
            {"exists": True, "path": str(target), "name": "target.mkv", "has_ptbr_audio": False, "streams": []},
            {"exists": True, "path": str(source), "name": "source.mkv", "has_ptbr_audio": False, "streams": []},
        ]

        plan = build_manual_plan(str(target), str(source), workspace)

    assert plan["ready"] is False
    assert "A fonte precisa ter audio PT-BR detectavel." in plan["problems"]


def test_build_manual_plan_returns_safe_output_path(tmp_path: Path):
    workspace = ensure_workspace(tmp_path)
    target = workspace.input_dir / "target.4k.mkv"
    source = workspace.input_dir / "source.1080p.mkv"
    target.write_bytes(b"target")
    source.write_bytes(b"source")

    with patch("src.web.ops.inspect_media_file") as inspect:
        inspect.side_effect = [
            {"exists": True, "path": str(target), "name": "target.4k.mkv", "has_ptbr_audio": False, "streams": []},
            {"exists": True, "path": str(source), "name": "source.1080p.mkv", "has_ptbr_audio": True, "ptbr_stream_index": 2, "streams": []},
        ]

        plan = build_manual_plan(str(target), str(source), workspace)

    assert plan["ready"] is True
    assert plan["ptbr_stream_index"] == 2
    assert plan["output_path"].endswith("target.4k.ptbrmerger.mkv")
    assert str(workspace.output_dir) in plan["output_path"]
    assert plan["will_replace_original"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest -q tests/test_web_ops.py::test_build_manual_plan_requires_source_with_ptbr_audio tests/test_web_ops.py::test_build_manual_plan_returns_safe_output_path -v
```

Expected:

```text
ImportError: cannot import name 'build_manual_plan'
```

- [ ] **Step 3: Implement manual plan**

Add to `src/web/ops.py`:

```python
def _safe_output_name(target: Path) -> str:
    stem = target.stem
    return f"{stem}.ptbrmerger.mkv"


def build_manual_plan(target_path: str, source_path: str, workspace: LocalWorkspace) -> dict:
    target = inspect_media_file(target_path, workspace)
    source = inspect_media_file(source_path, workspace)
    problems = []

    if not target.get("exists"):
        problems.append("Arquivo alvo 4K nao encontrado.")
    if not source.get("exists"):
        problems.append("Arquivo fonte PT-BR nao encontrado.")
    if target.get("exists") and source.get("exists") and target.get("path") == source.get("path"):
        problems.append("Alvo e fonte precisam ser arquivos diferentes.")
    if source.get("exists") and not source.get("has_ptbr_audio"):
        problems.append("A fonte precisa ter audio PT-BR detectavel.")

    output_path = ""
    if target.get("exists"):
        output_path = str(workspace.output_dir / _safe_output_name(Path(target["path"])))

    return {
        "ready": not problems,
        "problems": problems,
        "target": target,
        "source": source,
        "ptbr_stream_index": source.get("ptbr_stream_index"),
        "output_path": output_path,
        "will_replace_original": False,
        "summary": "Gerar novo MKV em output/ sem substituir o original.",
    }
```

- [ ] **Step 4: Run focused tests**

Run:

```bash
pytest -q tests/test_web_ops.py::test_build_manual_plan_requires_source_with_ptbr_audio tests/test_web_ops.py::test_build_manual_plan_returns_safe_output_path -v
```

Expected:

```text
2 passed
```

- [ ] **Step 5: Commit**

```bash
git add src/web/ops.py tests/test_web_ops.py
git commit -m "feat: plan safe manual recovery jobs"
```

---

### Task 5: Add Safe Manual Run, Report, And Recipe

**Files:**
- Modify: `src/web/ops.py`
- Test: `tests/test_web_ops.py`

- [ ] **Step 1: Write failing tests for manual run orchestration**

Append to `tests/test_web_ops.py`:

```python
import json

from src.web.ops import run_manual_plan


def test_run_manual_plan_writes_report_and_recipe_without_replacing_original(tmp_path: Path):
    workspace = ensure_workspace(tmp_path)
    target = workspace.input_dir / "target.mkv"
    source = workspace.input_dir / "source.mkv"
    target.write_bytes(b"target")
    source.write_bytes(b"source")

    plan = {
        "ready": True,
        "target": {"path": str(target), "name": "target.mkv"},
        "source": {"path": str(source), "name": "source.mkv"},
        "ptbr_stream_index": 1,
        "output_path": str(workspace.output_dir / "target.ptbrmerger.mkv"),
        "will_replace_original": False,
    }

    with patch("src.web.ops.merger.extract_audio", return_value=workspace.work_dir / "audio_ptbr.eac3") as extract:
        with patch("src.web.ops.merger.mux_audio", return_value=Path(plan["output_path"])) as mux:
            with patch("src.web.ops.analyzer.validate_final_file", return_value={"valid": True, "reason": "OK"}):
                result = run_manual_plan(plan, workspace)

    assert result["status"] == "SUCCESS"
    assert result["output_path"] == plan["output_path"]
    assert Path(result["report_path"]).exists()
    assert Path(result["recipe_path"]).exists()
    report = json.loads(Path(result["report_path"]).read_text(encoding="utf-8"))
    recipe = json.loads(Path(result["recipe_path"]).read_text(encoding="utf-8"))
    assert report["will_replace_original"] is False
    assert recipe["privacy"]["contains_media"] is False
    assert recipe["privacy"]["contains_magnet"] is False
    extract.assert_called_once()
    mux.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest -q tests/test_web_ops.py::test_run_manual_plan_writes_report_and_recipe_without_replacing_original -v
```

Expected:

```text
ImportError: cannot import name 'run_manual_plan'
```

- [ ] **Step 3: Implement safe manual run**

Add to `src/web/ops.py`:

```python
import json
from datetime import datetime, timezone

import src.merger as merger


def _job_id() -> str:
    return datetime.now(timezone.utc).strftime("manual-%Y%m%dT%H%M%SZ")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def run_manual_plan(plan: dict, workspace: LocalWorkspace) -> dict:
    if not plan.get("ready"):
        return {"status": "BLOCKED", "problems": plan.get("problems", [])}
    if plan.get("will_replace_original"):
        return {"status": "BLOCKED", "problems": ["Substituir original nao e permitido pelo modo web local."]}

    job_id = _job_id()
    target = Path(plan["target"]["path"])
    source = Path(plan["source"]["path"])
    output_path = Path(plan["output_path"])
    audio_path = workspace.work_dir / f"{job_id}.audio_ptbr.eac3"

    extracted = merger.extract_audio(source, int(plan["ptbr_stream_index"]), audio_path)
    merger.mux_audio(target, extracted, output_path)
    validation = analyzer.validate_final_file(output_path, target)

    status = "SUCCESS" if validation.get("valid") else "VALIDATION_FAILED"
    report = {
        "job_id": job_id,
        "status": status,
        "target": str(target),
        "source": str(source),
        "output_path": str(output_path),
        "will_replace_original": False,
        "validation": validation,
    }
    recipe = {
        "schema_version": 1,
        "job_id": job_id,
        "source_profile": source.suffix.lower().lstrip("."),
        "target_profile": target.suffix.lower().lstrip("."),
        "audio_track": "pt-BR",
        "ptbr_stream_index": plan.get("ptbr_stream_index"),
        "validation": validation,
        "privacy": {
            "contains_media": False,
            "contains_magnet": False,
            "contains_tracker": False,
            "contains_credentials": False,
        },
    }

    report_path = workspace.reports_dir / f"{job_id}.report.json"
    recipe_path = workspace.recipes_dir / f"{job_id}.recipe.json"
    _write_json(report_path, report)
    _write_json(recipe_path, recipe)
    return {
        "status": status,
        "job_id": job_id,
        "output_path": str(output_path),
        "report_path": str(report_path),
        "recipe_path": str(recipe_path),
        "validation": validation,
    }
```

- [ ] **Step 4: Run focused test**

Run:

```bash
pytest -q tests/test_web_ops.py::test_run_manual_plan_writes_report_and_recipe_without_replacing_original -v
```

Expected:

```text
1 passed
```

- [ ] **Step 5: Commit**

```bash
git add src/web/ops.py tests/test_web_ops.py
git commit -m "feat: run safe local manual recovery"
```

---

### Task 6: Add Local HTTP API

**Files:**
- Create: `src/web/server.py`
- Test: `tests/test_web_server.py`

- [ ] **Step 1: Write failing tests for route dispatch and local bind default**

Create `tests/test_web_server.py`:

```python
import json
from pathlib import Path
from unittest.mock import patch

from src.web.server import build_response, default_server_address


def test_default_server_address_binds_to_loopback_only():
    assert default_server_address() == ("127.0.0.1", 8787)


def test_build_response_status_route(tmp_path: Path):
    with patch("src.web.server.ops.build_local_status", return_value={"manual_ready": True}):
        status, headers, body = build_response("GET", "/api/status", b"", tmp_path)

    assert status == 200
    assert headers["Content-Type"] == "application/json; charset=utf-8"
    assert json.loads(body.decode("utf-8")) == {"manual_ready": True}


def test_build_response_rejects_unknown_route(tmp_path: Path):
    status, headers, body = build_response("GET", "/api/nope", b"", tmp_path)

    assert status == 404
    assert json.loads(body.decode("utf-8"))["error"] == "Rota nao encontrada."
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest -q tests/test_web_server.py
```

Expected:

```text
ModuleNotFoundError: No module named 'src.web.server'
```

- [ ] **Step 3: Implement route dispatcher and server**

Create `src/web/server.py`:

```python
from __future__ import annotations

import json
import mimetypes
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from src.web import ops

STATIC_DIR = Path(__file__).resolve().parent / "static"


def default_server_address() -> tuple[str, int]:
    return ("127.0.0.1", 8787)


def _json_response(payload: dict, status: int = 200) -> tuple[int, dict[str, str], bytes]:
    return (
        status,
        {"Content-Type": "application/json; charset=utf-8"},
        json.dumps(payload, ensure_ascii=False).encode("utf-8"),
    )


def _read_json(body: bytes) -> dict:
    if not body:
        return {}
    try:
        payload = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _static_response(path: str) -> tuple[int, dict[str, str], bytes]:
    relative = "index.html" if path in ("", "/") else path.lstrip("/")
    candidate = (STATIC_DIR / relative).resolve()
    if STATIC_DIR.resolve() not in candidate.parents and candidate != STATIC_DIR.resolve():
        return _json_response({"error": "Caminho invalido."}, status=400)
    if not candidate.exists() or not candidate.is_file():
        return _json_response({"error": "Arquivo estatico nao encontrado."}, status=404)
    content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
    return 200, {"Content-Type": content_type}, candidate.read_bytes()


def build_response(method: str, raw_path: str, body: bytes, root: Path) -> tuple[int, dict[str, str], bytes]:
    parsed = urlparse(raw_path)
    path = parsed.path
    workspace = ops.ensure_workspace(root)

    if method == "GET" and path == "/api/status":
        return _json_response(ops.build_local_status(root))
    if method == "GET" and path == "/api/input-files":
        return _json_response({"files": ops.list_input_files(workspace)})
    if method == "POST" and path == "/api/inspect":
        payload = _read_json(body)
        return _json_response(ops.inspect_media_file(str(payload.get("path") or ""), workspace))
    if method == "POST" and path == "/api/manual-plan":
        payload = _read_json(body)
        return _json_response(
            ops.build_manual_plan(
                str(payload.get("target_path") or ""),
                str(payload.get("source_path") or ""),
                workspace,
            )
        )
    if method == "POST" and path == "/api/manual-run":
        payload = _read_json(body)
        plan = payload.get("plan") if isinstance(payload.get("plan"), dict) else {}
        return _json_response(ops.run_manual_plan(plan, workspace))
    if method == "GET" and not path.startswith("/api/"):
        return _static_response(path)
    return _json_response({"error": "Rota nao encontrada."}, status=404)


class PTBRMergerHandler(BaseHTTPRequestHandler):
    root_dir = Path.cwd()

    def _send(self, status: int, headers: dict[str, str], body: bytes) -> None:
        self.send_response(status)
        for key, value in headers.items():
            self.send_header(key, value)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        self._send(*build_response("GET", self.path, b"", self.root_dir))

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length) if length else b""
        self._send(*build_response("POST", self.path, body, self.root_dir))


def main() -> None:
    host, port = default_server_address()
    PTBRMergerHandler.root_dir = Path.cwd()
    server = ThreadingHTTPServer((host, port), PTBRMergerHandler)
    url = f"http://{host}:{port}"
    print(f"PTBRMerger local web mode: {url}")
    webbrowser.open(url)
    server.serve_forever()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run server tests**

Run:

```bash
pytest -q tests/test_web_server.py
```

Expected:

```text
3 passed
```

- [ ] **Step 5: Commit**

```bash
git add src/web/server.py tests/test_web_server.py
git commit -m "feat: add local web recovery API"
```

---

### Task 7: Add One-Screen Local Web UI

**Files:**
- Create: `src/web/static/index.html`
- Create: `src/web/static/styles.css`
- Create: `src/web/static/app.js`

- [ ] **Step 1: Create the HTML shell**

Create `src/web/static/index.html`:

```html
<!doctype html>
<html lang="pt-BR">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>PTBRMerger Local Recovery</title>
    <link rel="stylesheet" href="/styles.css" />
  </head>
  <body>
    <main class="shell">
      <header class="topbar">
        <div>
          <p class="eyebrow">PTBRMerger</p>
          <h1>Retomada local</h1>
        </div>
        <button id="refresh-status" type="button">Atualizar</button>
      </header>

      <section class="status-band" aria-live="polite">
        <h2>Ambiente</h2>
        <p id="status-summary">Carregando diagnostico...</p>
        <div id="status-checks" class="checks"></div>
      </section>

      <section class="workspace">
        <h2>Arquivos locais</h2>
        <p id="workspace-path"></p>
        <button id="load-files" type="button">Listar pasta input</button>
        <div class="picker-row">
          <label>
            Alvo 4K
            <select id="target-select"></select>
          </label>
          <label>
            Fonte PT-BR
            <select id="source-select"></select>
          </label>
        </div>
        <div class="picker-row">
          <label>
            Ou cole caminho do alvo
            <input id="target-path" type="text" />
          </label>
          <label>
            Ou cole caminho da fonte
            <input id="source-path" type="text" />
          </label>
        </div>
        <button id="inspect-files" type="button">Inspecionar</button>
      </section>

      <section class="plan">
        <h2>Plano manual</h2>
        <pre id="plan-output">Nenhum plano criado.</pre>
        <div class="actions">
          <button id="build-plan" type="button">Criar plano</button>
          <button id="run-plan" type="button" disabled>Gerar arquivo final</button>
        </div>
      </section>

      <section class="result">
        <h2>Resultado</h2>
        <pre id="result-output">Aguardando execucao.</pre>
      </section>
    </main>
    <script src="/app.js"></script>
  </body>
</html>
```

- [ ] **Step 2: Create the CSS**

Create `src/web/static/styles.css`:

```css
:root {
  color-scheme: dark;
  --bg: #101113;
  --panel: #181b1f;
  --panel-strong: #20252b;
  --text: #f2f0ea;
  --muted: #a9b0b7;
  --line: #343a42;
  --accent: #59d6a3;
  --warn: #e5b454;
  --bad: #ef6f6c;
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font-family: Arial, Helvetica, sans-serif;
}

button,
input,
select {
  font: inherit;
}

button {
  border: 1px solid var(--line);
  background: var(--panel-strong);
  color: var(--text);
  border-radius: 6px;
  padding: 10px 14px;
  cursor: pointer;
}

button:disabled {
  cursor: not-allowed;
  opacity: 0.45;
}

.shell {
  width: min(1120px, calc(100vw - 32px));
  margin: 0 auto;
  padding: 28px 0 48px;
}

.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 20px;
}

.eyebrow {
  margin: 0 0 4px;
  color: var(--accent);
  font-size: 13px;
  text-transform: uppercase;
}

h1,
h2 {
  margin: 0;
  letter-spacing: 0;
}

h1 {
  font-size: 32px;
}

h2 {
  font-size: 18px;
  margin-bottom: 12px;
}

section {
  border-top: 1px solid var(--line);
  padding: 22px 0;
}

.status-band,
.workspace,
.plan,
.result {
  background: transparent;
}

.checks {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 8px;
  margin-top: 12px;
}

.check {
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 10px;
  background: var(--panel);
}

.check strong {
  display: block;
  margin-bottom: 4px;
}

.check small {
  color: var(--muted);
}

.picker-row {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-top: 12px;
}

label {
  display: grid;
  gap: 6px;
  color: var(--muted);
}

input,
select {
  width: 100%;
  border: 1px solid var(--line);
  background: var(--panel);
  color: var(--text);
  border-radius: 6px;
  padding: 10px;
}

pre {
  min-height: 120px;
  overflow: auto;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: #0b0c0e;
  color: var(--text);
  padding: 12px;
  white-space: pre-wrap;
}

.actions {
  display: flex;
  gap: 10px;
}

@media (max-width: 760px) {
  .topbar,
  .picker-row,
  .actions {
    grid-template-columns: 1fr;
    flex-direction: column;
    align-items: stretch;
  }
}
```

- [ ] **Step 3: Create the JavaScript**

Create `src/web/static/app.js`:

```javascript
let currentPlan = null;

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });
  return response.json();
}

function text(id, value) {
  document.getElementById(id).textContent = value;
}

function selectedOrTyped(selectId, inputId) {
  const typed = document.getElementById(inputId).value.trim();
  if (typed) return typed;
  return document.getElementById(selectId).value;
}

function renderJson(id, payload) {
  text(id, JSON.stringify(payload, null, 2));
}

async function loadStatus() {
  const status = await api("/api/status");
  text("status-summary", status.summary || "Sem resumo.");
  text("workspace-path", status.workspace ? `Pasta input: ${status.workspace.input_dir}` : "");
  const checks = document.getElementById("status-checks");
  checks.innerHTML = "";
  Object.values(status.checks || {}).forEach((check) => {
    const node = document.createElement("div");
    node.className = "check";
    node.innerHTML = `<strong>${check.name}: ${check.status}</strong><small>${check.message}</small>`;
    checks.appendChild(node);
  });
}

async function loadFiles() {
  const payload = await api("/api/input-files");
  const target = document.getElementById("target-select");
  const source = document.getElementById("source-select");
  target.innerHTML = "";
  source.innerHTML = "";
  (payload.files || []).forEach((file) => {
    const first = new Option(file.name, file.path);
    const second = new Option(file.name, file.path);
    target.add(first);
    source.add(second);
  });
}

async function inspectFiles() {
  const target = selectedOrTyped("target-select", "target-path");
  const source = selectedOrTyped("source-select", "source-path");
  const targetInspect = await api("/api/inspect", { method: "POST", body: JSON.stringify({ path: target }) });
  const sourceInspect = await api("/api/inspect", { method: "POST", body: JSON.stringify({ path: source }) });
  renderJson("plan-output", { target: targetInspect, source: sourceInspect });
}

async function buildPlan() {
  const target = selectedOrTyped("target-select", "target-path");
  const source = selectedOrTyped("source-select", "source-path");
  currentPlan = await api("/api/manual-plan", {
    method: "POST",
    body: JSON.stringify({ target_path: target, source_path: source }),
  });
  renderJson("plan-output", currentPlan);
  document.getElementById("run-plan").disabled = !currentPlan.ready;
}

async function runPlan() {
  if (!currentPlan || !currentPlan.ready) return;
  const result = await api("/api/manual-run", {
    method: "POST",
    body: JSON.stringify({ plan: currentPlan }),
  });
  renderJson("result-output", result);
}

document.getElementById("refresh-status").addEventListener("click", loadStatus);
document.getElementById("load-files").addEventListener("click", loadFiles);
document.getElementById("inspect-files").addEventListener("click", inspectFiles);
document.getElementById("build-plan").addEventListener("click", buildPlan);
document.getElementById("run-plan").addEventListener("click", runPlan);

loadStatus();
loadFiles();
```

- [ ] **Step 4: Run a static route smoke test**

Run:

```bash
pytest -q tests/test_web_server.py
```

Expected:

```text
3 passed
```

- [ ] **Step 5: Commit**

```bash
git add src/web/static/index.html src/web/static/styles.css src/web/static/app.js
git commit -m "feat: add local recovery web UI"
```

---

### Task 8: Add Windows Launcher

**Files:**
- Create: `START_PTBRMERGER.bat`

- [ ] **Step 1: Create launcher**

Create `START_PTBRMERGER.bat`:

```bat
@echo off
setlocal
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Python nao encontrado no PATH.
  echo Instale Python 3.11+ ou rode com o caminho completo do python.exe.
  pause
  exit /b 1
)
python -m src.web.server
pause
```

- [ ] **Step 2: Smoke check module import**

Run:

```bash
python -m compileall src/web
```

Expected:

```text
Listing 'src/web'...
```

- [ ] **Step 3: Commit**

```bash
git add START_PTBRMERGER.bat
git commit -m "feat: add local web launcher"
```

---

### Task 9: Update Roadmap And Operator Docs

**Files:**
- Modify: `.planning/ROADMAP.md`
- Modify: `.planning/PROJECT.md`
- Modify: `README.md`

- [ ] **Step 1: Update roadmap milestone name and phase goals**

In `.planning/ROADMAP.md`, replace the active milestone title:

```markdown
🚧 **v0.4.5 Guided Operations** - Phases 6-9 (planned)
```

with:

```markdown
🚧 **v0.4.5 Post-Format Recovery Web Mode** - Phases 6-9 (planned)
```

Replace the Phase 6-9 table with:

```markdown
| # | Phase | Goal | Requirements | Success Criteria |
|---|-------|------|--------------|------------------|
| 6 | Local Web Launcher | Start a localhost recovery surface with one Windows launcher and no Node/React dependency | OPS-01, OPS-02 | 4 |
| 7 | Web Doctor And Workspace | Show manual-vs-automation readiness and create local input/output/report/recipe folders | DOC-01, DOC-02, DOC-03 | 4 |
| 8 | Manual Recovery Web Flow | Let the operator inspect two local MKVs, review a safe plan, and generate a new output file without replacing the original | REC-UX-01, REC-UX-02, REC-UX-03, SAFE-OPS-02 | 4 |
| 9 | Reports, Recipes, And Recovery Docs | Save human-readable reports and privacy-safe recipes, then document the post-format path in Portuguese | GUIDE-01 | 3 |
```

- [ ] **Step 2: Update project decision**

In `.planning/PROJECT.md`, add this row to the Key Decisions table:

```markdown
| Make web local the primary v0.4.5 recovery UX | The user is blocked by CLI friction after formatting the PC; a localhost screen opened by `.bat` gives value faster without jumping to desktop/cloud | Pending |
```

- [ ] **Step 3: Add README quick path**

In `README.md`, add this section before `## Installation`:

```markdown
## Retomada pos-formatacao

Se voce formatou o PC e nao quer reconfigurar Radarr, qBittorrent, Bazarr e Discord agora, use o modo web local:

```bat
START_PTBRMERGER.bat
```

Ele abre `http://127.0.0.1:8787` e permite:

- ver o que ainda funciona no ambiente atual;
- usar a pasta `input/` para colocar dois arquivos locais;
- inspecionar um alvo 4K e uma fonte 1080p com audio PT-BR;
- revisar um plano seguro;
- gerar um novo MKV em `output/` sem substituir o original;
- salvar um relatorio e uma receita tecnica local.

Este modo nao baixa filmes, nao acessa trackers, nao envia dados para cloud e nao configura servicos externos automaticamente.
```

- [ ] **Step 4: Commit**

```bash
git add .planning/ROADMAP.md .planning/PROJECT.md README.md
git commit -m "docs: define post-format web recovery milestone"
```

---

### Task 10: Validate End To End Locally

**Files:**
- No planned source edits. Fix only issues found by validation.

- [ ] **Step 1: Run unit tests for new surface**

Run:

```bash
pytest -q tests/test_web_ops.py tests/test_web_server.py
```

Expected:

```text
all tests pass
```

- [ ] **Step 2: Run existing tool tests**

Run:

```bash
pytest -q tests/test_tools.py
```

Expected:

```text
all tests pass
```

- [ ] **Step 3: Run compile check**

Run:

```bash
python -m compileall src tests
```

Expected:

```text
no syntax errors
```

- [ ] **Step 4: Start local server**

Run:

```bash
python -m src.web.server
```

Expected:

```text
PTBRMerger local web mode: http://127.0.0.1:8787
```

- [ ] **Step 5: Browser validation**

Use Browser Use to open:

```text
http://127.0.0.1:8787
```

Verify:

- page loads;
- status section renders;
- Radarr/qBittorrent can be unavailable without hiding manual mode;
- input file list button does not crash on empty `input/`;
- plan button reports missing files clearly;
- no request is made to any non-local URL;
- console has no runtime errors.

- [ ] **Step 6: Commit final fixes if needed**

```bash
git add <fixed-files>
git commit -m "fix: harden local web recovery validation"
```

---

## Self-Review

**Spec coverage:** The plan covers the final decision: web local primary UX, post-format recovery, no external stack requirement, manual two-file value path, safe output, report/recipe, and docs.

**Placeholder scan:** No task uses TBD/TODO/fill-later language. Every implementation task includes concrete code or exact edit text.

**Type consistency:** The plan consistently uses `LocalWorkspace`, `ensure_workspace`, `build_local_status`, `list_input_files`, `inspect_media_file`, `build_manual_plan`, and `run_manual_plan`.

**Risk controls:**

- Server binds to `127.0.0.1`.
- No CORS support is added.
- No upload endpoint is added.
- No arbitrary command endpoint is added.
- Manual web flow never replaces originals.
- External integrations remain optional for this milestone.
