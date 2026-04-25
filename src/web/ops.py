from __future__ import annotations

import json
import hashlib
import shutil
import subprocess
import threading
import urllib.request
import webbrowser
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import src.analyzer as analyzer
import src.config as config_module
import src.merger as merger
from src.tools.preflight import run_preflight
import yaml


@dataclass(frozen=True)
class LocalWorkspace:
    root: Path
    input_dir: Path
    output_dir: Path
    work_dir: Path
    reports_dir: Path
    recipes_dir: Path
    logs_dir: Path


MANUAL_REQUIRED_CHECKS = {"ffmpeg", "ffprobe"}
AUTOMATION_REQUIRED_CHECKS = {"radarr", "qbittorrent"}
OPENABLE_WORKSPACE_LOCATIONS = {
    "input": "input_dir",
    "output": "output_dir",
    "reports": "reports_dir",
    "recipes": "recipes_dir",
}
FFMPEG_RELEASE_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
FFMPEG_SHA256_URL = FFMPEG_RELEASE_URL + ".sha256"
LOCAL_TOOLS_DIR = "tools"
INSTALL_STATE_LOCK = threading.Lock()
INSTALL_STATE: dict = {
    "status": "IDLE",
    "message": "Nenhuma instalação em andamento.",
    "progress": 0,
}


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


def _is_mkv_file(path: Path) -> bool:
    return path.suffix.lower() == ".mkv"


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
        summary = "Modo manual disponível. Automação externa incompleta."
    elif manual_ready and automation_ready:
        summary = "Modo manual e automação externa disponíveis."
    else:
        summary = "Workspace criado. Para inspecionar e muxar, configure FFmpeg/FFprobe."

    return {
        "mode": "manual-recovery",
        "manual_ready": manual_ready,
        "automation_ready": automation_ready,
        "workspace_ready": True,
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


def _run_version(executable: str) -> dict:
    try:
        process = subprocess.run(
            [executable, "-version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
    except Exception as exc:
        return {"available": False, "error": str(exc)}

    first_line = (process.stdout or "").splitlines()[0] if process.stdout else "versão não informada"
    return {"available": True, "version": first_line}


def _resolve_tool(path_or_name: str) -> str:
    value = str(path_or_name or "").strip()
    if not value:
        return ""
    resolved = shutil.which(value)
    if resolved:
        return resolved
    candidate = Path(value)
    if candidate.exists():
        return str(candidate.resolve())
    return value


def dependency_status(root: Path | None = None) -> dict:
    workspace = ensure_workspace(root)
    cfg = config_module.get_config()
    ffmpeg_path = _resolve_tool(cfg.ffmpeg.ffmpeg_path)
    ffprobe_path = _resolve_tool(cfg.ffmpeg.ffprobe_path)
    ffmpeg_version = _run_version(ffmpeg_path) if ffmpeg_path else {"available": False, "error": "not-configured"}
    ffprobe_version = _run_version(ffprobe_path) if ffprobe_path else {"available": False, "error": "not-configured"}
    return {
        "ready": bool(ffmpeg_version.get("available") and ffprobe_version.get("available")),
        "install_source": FFMPEG_RELEASE_URL,
        "local_tools_dir": str((workspace.root / LOCAL_TOOLS_DIR / "ffmpeg").resolve()),
        "ffmpeg": {
            "configured": cfg.ffmpeg.ffmpeg_path,
            "resolved_path": ffmpeg_path,
            **ffmpeg_version,
        },
        "ffprobe": {
            "configured": cfg.ffmpeg.ffprobe_path,
            "resolved_path": ffprobe_path,
            **ffprobe_version,
        },
        "safety": {
            "requires_admin": False,
            "changes_global_path": False,
            "installs_locally": True,
        },
    }


def web_settings(root: Path | None = None) -> dict:
    workspace = ensure_workspace(root)
    return {
        "theme": {"default": "system", "allowed": ["system", "light", "dark"]},
        "workspace": {
            "input_dir": str(workspace.input_dir),
            "output_dir": str(workspace.output_dir),
            "reports_dir": str(workspace.reports_dir),
            "recipes_dir": str(workspace.recipes_dir),
            "tools_dir": str(workspace.root / LOCAL_TOOLS_DIR),
        },
        "dependencies": dependency_status(workspace.root),
    }


def save_web_theme(theme: str) -> dict:
    value = str(theme or "").strip().lower()
    if value not in {"system", "light", "dark"}:
        return {"status": "BLOCKED", "error": "Tema inválido."}
    return {"status": "SAVED", "theme": value}


def _install_state(**updates) -> dict:
    with INSTALL_STATE_LOCK:
        INSTALL_STATE.update(updates)
        return dict(INSTALL_STATE)


def ffmpeg_install_status() -> dict:
    try:
        deps = dependency_status()
    except Exception:
        deps = {"ready": False}
    with INSTALL_STATE_LOCK:
        if deps.get("ready") and INSTALL_STATE.get("status") in {"IDLE", "RUNNING", "INSTALLED"}:
            INSTALL_STATE.update(
                {
                    "status": "INSTALLED",
                    "message": "FFmpeg e FFprobe estao prontos.",
                    "progress": 100,
                }
            )
        return dict(INSTALL_STATE)


def _download(url: str, destination: Path, *, label: str = "download") -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=60) as response:
        total = int(response.headers.get("Content-Length") or "0")
        downloaded = 0
        with destination.open("wb") as handle:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
                downloaded += len(chunk)
                if total > 0:
                    progress = min(90, int(downloaded * 80 / total) + 8)
                    _install_state(
                        status="RUNNING",
                        message=f"Baixando {label}: {downloaded // (1024 * 1024)} MB de {total // (1024 * 1024)} MB.",
                        progress=progress,
                    )
                else:
                    _install_state(
                        status="RUNNING",
                        message=f"Baixando {label}: {downloaded // (1024 * 1024)} MB.",
                        progress=20,
                    )


def _expected_sha256(raw_text: str) -> str:
    first_token = str(raw_text or "").strip().split()[0]
    if len(first_token) != 64 or any(char not in "0123456789abcdefABCDEF" for char in first_token):
        raise ValueError("SHA256 remoto inválido.")
    return first_token.lower()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _extract_ffmpeg_bins(archive_path: Path, install_dir: Path) -> tuple[Path, Path]:
    install_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path) as archive:
        members = {name.replace("\\", "/"): name for name in archive.namelist()}
        wanted = {}
        for normalized, original in members.items():
            lower = normalized.lower()
            if lower.endswith("/bin/ffmpeg.exe"):
                wanted["ffmpeg"] = original
            if lower.endswith("/bin/ffprobe.exe"):
                wanted["ffprobe"] = original
        if set(wanted) != {"ffmpeg", "ffprobe"}:
            raise FileNotFoundError("Pacote FFmpeg sem ffmpeg.exe/ffprobe.exe.")
        ffmpeg_path = install_dir / "ffmpeg.exe"
        ffprobe_path = install_dir / "ffprobe.exe"
        for key, output_path in (("ffmpeg", ffmpeg_path), ("ffprobe", ffprobe_path)):
            with archive.open(wanted[key]) as source:
                output_path.write_bytes(source.read())
    return ffmpeg_path, ffprobe_path


def _load_config_yaml(root: Path) -> tuple[Path, dict]:
    config_path = root / "config.yml"
    source_path = config_path if config_path.exists() else root / "config.example.yml"
    if not source_path.exists():
        raise FileNotFoundError("config.yml/config.example.yml não encontrado.")
    payload = yaml.safe_load(source_path.read_text(encoding="utf-8")) or {}
    return config_path, payload


def _save_ffmpeg_config(root: Path, ffmpeg_path: Path, ffprobe_path: Path) -> None:
    config_path, payload = _load_config_yaml(root)
    payload.setdefault("ffmpeg", {})
    payload["ffmpeg"]["ffmpeg_path"] = str(ffmpeg_path)
    payload["ffmpeg"]["ffprobe_path"] = str(ffprobe_path)
    config_path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")

    config_module._config_instance = None
    refreshed = config_module.get_config()
    analyzer.config = refreshed
    merger.config = refreshed


def _local_ffmpeg_pair(workspace: LocalWorkspace) -> tuple[Path, Path]:
    tools_root = workspace.root / LOCAL_TOOLS_DIR / "ffmpeg"
    return tools_root / "ffmpeg.exe", tools_root / "ffprobe.exe"


def _use_installed_local_ffmpeg_if_ready(workspace: LocalWorkspace) -> dict | None:
    ffmpeg_path, ffprobe_path = _local_ffmpeg_pair(workspace)
    if not ffmpeg_path.exists() or not ffprobe_path.exists():
        return None

    ffmpeg_version = _run_version(str(ffmpeg_path))
    ffprobe_version = _run_version(str(ffprobe_path))
    if not ffmpeg_version.get("available") or not ffprobe_version.get("available"):
        return None

    _save_ffmpeg_config(workspace.root, ffmpeg_path, ffprobe_path)
    return {
        "status": "INSTALLED",
        "message": "FFmpeg local já instalado; caminhos atualizados para este app.",
        "progress": 100,
        "ffmpeg_path": str(ffmpeg_path),
        "ffprobe_path": str(ffprobe_path),
        "ffmpeg_version": ffmpeg_version.get("version"),
        "ffprobe_version": ffprobe_version.get("version"),
        "source": "local-existing",
        "changed_global_path": False,
    }


def install_local_ffmpeg(root: Path | None = None) -> dict:
    workspace = ensure_workspace(root)
    local_ready = _use_installed_local_ffmpeg_if_ready(workspace)
    if local_ready is not None:
        _install_state(**local_ready)
        return local_ready

    ready = dependency_status(workspace.root)
    if ready.get("ready"):
        result = {
            "status": "INSTALLED",
            "message": "FFmpeg e FFprobe já estão prontos.",
            "progress": 100,
            "ffmpeg_path": ready.get("ffmpeg", {}).get("resolved_path", ""),
            "ffprobe_path": ready.get("ffprobe", {}).get("resolved_path", ""),
            "ffmpeg_version": ready.get("ffmpeg", {}).get("version"),
            "ffprobe_version": ready.get("ffprobe", {}).get("version"),
            "source": ready.get("install_source", FFMPEG_RELEASE_URL),
            "changed_global_path": False,
        }
        _install_state(**result)
        return result

    tools_root = workspace.root / LOCAL_TOOLS_DIR / "ffmpeg"
    downloads_dir = workspace.root / "tmp" / "downloads"
    archive_path = downloads_dir / "ffmpeg-release-essentials.zip"
    sha_path = downloads_dir / "ffmpeg-release-essentials.zip.sha256"

    try:
        _install_state(status="RUNNING", message="Baixando checksum do FFmpeg.", progress=4)
        _download(FFMPEG_SHA256_URL, sha_path, label="checksum")
        _install_state(status="RUNNING", message="Baixando pacote do FFmpeg.", progress=8)
        _download(FFMPEG_RELEASE_URL, archive_path, label="FFmpeg")
        _install_state(status="RUNNING", message="Validando checksum SHA256.", progress=92)
        expected = _expected_sha256(sha_path.read_text(encoding="utf-8", errors="replace"))
        actual = _sha256(archive_path)
        if actual != expected:
            result = {"status": "BLOCKED", "error": "Checksum SHA256 não confere.", "expected": expected, "actual": actual}
            _install_state(**result, message=result["error"], progress=100)
            return result

        _install_state(status="RUNNING", message="Extraindo ffmpeg.exe e ffprobe.exe.", progress=95)
        ffmpeg_path, ffprobe_path = _extract_ffmpeg_bins(archive_path, tools_root)
        _install_state(status="RUNNING", message="Validando binarios extraidos.", progress=98)
        ffmpeg_version = _run_version(str(ffmpeg_path))
        ffprobe_version = _run_version(str(ffprobe_path))
        if not ffmpeg_version.get("available") or not ffprobe_version.get("available"):
            result = {"status": "BLOCKED", "error": "Binários extraídos, mas validação de versão falhou."}
            _install_state(**result, message=result["error"], progress=100)
            return result
        _save_ffmpeg_config(workspace.root, ffmpeg_path, ffprobe_path)
    except Exception as exc:
        result = {"status": "ERROR", "error": str(exc)}
        _install_state(**result, message=f"Instalação falhou: {exc}", progress=100)
        return result

    result = {
        "status": "INSTALLED",
        "ffmpeg_path": str(ffmpeg_path),
        "ffprobe_path": str(ffprobe_path),
        "ffmpeg_version": ffmpeg_version.get("version"),
        "ffprobe_version": ffprobe_version.get("version"),
        "source": FFMPEG_RELEASE_URL,
        "changed_global_path": False,
    }
    _install_state(**result, message="FFmpeg instalado para este app.", progress=100)
    return result


def start_local_ffmpeg_install(root: Path | None = None) -> dict:
    workspace = ensure_workspace(root)
    local_ready = _use_installed_local_ffmpeg_if_ready(workspace)
    if local_ready is not None:
        return _install_state(**local_ready)

    ready = dependency_status(workspace.root)
    if ready.get("ready"):
        result = {
            "status": "INSTALLED",
            "message": "FFmpeg e FFprobe já estão prontos.",
            "progress": 100,
            "ffmpeg_path": ready.get("ffmpeg", {}).get("resolved_path", ""),
            "ffprobe_path": ready.get("ffprobe", {}).get("resolved_path", ""),
            "ffmpeg_version": ready.get("ffmpeg", {}).get("version"),
            "ffprobe_version": ready.get("ffprobe", {}).get("version"),
            "source": ready.get("install_source", FFMPEG_RELEASE_URL),
            "changed_global_path": False,
        }
        return _install_state(**result)

    with INSTALL_STATE_LOCK:
        if INSTALL_STATE.get("status") == "RUNNING":
            return dict(INSTALL_STATE)
        INSTALL_STATE.clear()
        INSTALL_STATE.update(
            {
                "status": "RUNNING",
                "message": "Preparando instalação local do FFmpeg.",
                "progress": 1,
                "source": FFMPEG_RELEASE_URL,
            }
        )

    thread = threading.Thread(target=install_local_ffmpeg, args=(workspace.root,), daemon=True)
    thread.start()
    return ffmpeg_install_status()


def use_local_tools(ffmpeg_raw: str, ffprobe_raw: str, root: Path | None = None) -> dict:
    workspace = ensure_workspace(root)
    ffmpeg_path = resolve_user_path(ffmpeg_raw, workspace)
    ffprobe_path = resolve_user_path(ffprobe_raw, workspace)
    if ffmpeg_path is None or ffmpeg_path.name.lower() != "ffmpeg.exe":
        return {"status": "BLOCKED", "error": "Selecione um ffmpeg.exe válido."}
    if ffprobe_path is None or ffprobe_path.name.lower() != "ffprobe.exe":
        return {"status": "BLOCKED", "error": "Selecione um ffprobe.exe válido."}

    ffmpeg_version = _run_version(str(ffmpeg_path))
    ffprobe_version = _run_version(str(ffprobe_path))
    if not ffmpeg_version.get("available"):
        return {"status": "BLOCKED", "error": "ffmpeg.exe não respondeu a -version."}
    if not ffprobe_version.get("available"):
        return {"status": "BLOCKED", "error": "ffprobe.exe não respondeu a -version."}

    _save_ffmpeg_config(workspace.root, ffmpeg_path, ffprobe_path)
    return {
        "status": "SAVED",
        "ffmpeg_path": str(ffmpeg_path),
        "ffprobe_path": str(ffprobe_path),
        "ffmpeg_version": ffmpeg_version.get("version"),
        "ffprobe_version": ffprobe_version.get("version"),
    }


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
        return {"exists": False, "error": "Arquivo não encontrado."}
    if not _is_mkv_file(path):
        return {"exists": False, "error": "Selecione um arquivo .mkv."}

    try:
        probe = analyzer._probe_file(path)
        streams = [_stream_summary(stream) for stream in probe.get("streams", [])]
        duration_raw = probe.get("format", {}).get("duration", "0")
        try:
            duration = float(duration_raw)
        except (TypeError, ValueError):
            duration = 0.0
        ptbr_stream_index = analyzer.get_ptbr_stream_index(path)
    except Exception:
        return {
            "exists": True,
            "path": str(path),
            "name": path.name,
            "error": "Nao foi possivel inspecionar este MKV com ffprobe.",
        }
    return {
        "exists": True,
        "path": str(path),
        "name": path.name,
        "duration_seconds": duration,
        "has_ptbr_audio": ptbr_stream_index is not None,
        "ptbr_stream_index": ptbr_stream_index,
        "streams": streams,
    }


def _safe_output_name(target: Path) -> str:
    stem = target.stem
    return f"{stem}.ptbrmerger.mkv"


def _safe_output_path(target: Path, workspace: LocalWorkspace) -> Path:
    base = workspace.output_dir / _safe_output_name(target)
    if not base.exists():
        return base
    for index in range(2, 100):
        candidate = workspace.output_dir / f"{target.stem}.ptbrmerger-{index}.mkv"
        if not candidate.exists():
            return candidate
    raise RuntimeError("Não foi possível sugerir um nome de saída livre.")


def build_manual_plan(target_path: str, source_path: str, workspace: LocalWorkspace) -> dict:
    target = inspect_media_file(target_path, workspace)
    source = inspect_media_file(source_path, workspace)
    problems = []

    if not target.get("exists"):
        problems.append("Arquivo alvo 4K não encontrado.")
    if not source.get("exists"):
        problems.append("Arquivo fonte PT-BR não encontrado.")
    if target.get("exists") and source.get("exists") and target.get("path") == source.get("path"):
        problems.append("Alvo e fonte precisam ser arquivos diferentes.")
    if source.get("exists") and not source.get("has_ptbr_audio"):
        problems.append("A fonte precisa ter áudio PT-BR detectável.")

    output_path = ""
    if target.get("exists"):
        output_path = str(_safe_output_path(Path(target["path"]), workspace))

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


def _job_id() -> str:
    return datetime.now(timezone.utc).strftime("manual-%Y%m%dT%H%M%S%fZ")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _is_within(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def _sanitized_file(path: Path) -> dict:
    return {
        "name": path.name,
        "suffix": path.suffix.lower().lstrip("."),
    }


def open_workspace_location(location: str, workspace: LocalWorkspace) -> dict:
    key = str(location or "").strip().lower()
    attr = OPENABLE_WORKSPACE_LOCATIONS.get(key)
    if attr is None:
        return {"status": "BLOCKED", "error": "Local não permitido."}
    path = getattr(workspace, attr)
    path.mkdir(parents=True, exist_ok=True)
    webbrowser.open(path.resolve().as_uri())
    return {"status": "OPENED", "location": key, "path": str(path)}


def run_manual_plan(plan: dict, workspace: LocalWorkspace) -> dict:
    if not plan.get("ready"):
        return {"status": "BLOCKED", "problems": plan.get("problems", [])}
    if plan.get("will_replace_original"):
        return {"status": "BLOCKED", "problems": ["Substituir original não é permitido pelo modo web local."]}

    job_id = _job_id()
    target = Path(plan["target"]["path"])
    source = Path(plan["source"]["path"])
    output_path = Path(plan["output_path"])
    problems = []
    if not target.exists() or not target.is_file():
        problems.append("Arquivo alvo 4K não encontrado.")
    if not source.exists() or not source.is_file():
        problems.append("Arquivo fonte PT-BR não encontrado.")
    if target.exists() and target.is_file() and not _is_mkv_file(target):
        problems.append("Arquivo alvo precisa ser .mkv.")
    if source.exists() and source.is_file() and not _is_mkv_file(source):
        problems.append("Arquivo fonte precisa ser .mkv.")
    if not _is_within(output_path, workspace.output_dir):
        problems.append("A saída precisa ficar dentro da pasta output/.")
    if output_path.exists():
        problems.append("O arquivo de saída já existe. Recrie o plano para sugerir outro nome.")
    if problems:
        return {"status": "BLOCKED", "problems": problems}

    stream_index = analyzer.get_ptbr_stream_index(source) if source.exists() and source.is_file() else None
    if stream_index is None:
        problems.append("A fonte precisa ter áudio PT-BR detectável.")
    elif int(plan.get("ptbr_stream_index", -1)) != int(stream_index):
        problems.append("O índice PT-BR mudou; recrie o plano antes de executar.")
    if problems:
        return {"status": "BLOCKED", "problems": problems}

    audio_path = workspace.work_dir / f"{job_id}.audio_ptbr.eac3"

    extracted = merger.extract_audio(source, int(stream_index), audio_path)
    merger.mux_audio(target, extracted, output_path)
    validation = analyzer.validate_final_file(output_path, target)

    status = "SUCCESS" if validation.get("valid") else "VALIDATION_FAILED"
    report = {
        "job_id": job_id,
        "status": status,
        "target": _sanitized_file(target),
        "source": _sanitized_file(source),
        "output": _sanitized_file(output_path),
        "will_replace_original": False,
        "validation": validation,
    }
    recipe = {
        "schema_version": 1,
        "job_id": job_id,
        "source_profile": source.suffix.lower().lstrip("."),
        "target_profile": target.suffix.lower().lstrip("."),
        "audio_track": "pt-BR",
        "ptbr_stream_index": stream_index,
        "validation": validation,
        "workspace_locations": {
            "input": "input/",
            "output": "output/",
            "reports": "reports/",
            "recipes": "recipes/",
        },
        "privacy": {
            "contains_media": False,
            "contains_magnet": False,
            "contains_tracker": False,
            "contains_credentials": False,
            "contains_absolute_paths": False,
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
