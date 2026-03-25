import argparse
import json
import shutil
from pathlib import Path

import requests

from src.config import get_config
from src.qbit_client import login as qbit_login


def _check_executable(path_or_name: str, label: str) -> dict:
    candidate = str(path_or_name or "").strip()
    if not candidate:
        return {"name": label, "status": "BLOCKER", "message": "not-configured"}

    resolved = shutil.which(candidate)
    if resolved:
        return {"name": label, "status": "OK", "message": "available", "details": {"resolved_path": resolved}}

    candidate_path = Path(candidate)
    if candidate_path.exists():
        return {"name": label, "status": "OK", "message": "available", "details": {"resolved_path": str(candidate_path)}}

    return {"name": label, "status": "BLOCKER", "message": "not-found", "details": {"configured_path": candidate}}


def _check_json_file(path: Path, expected_type: type, label: str) -> dict:
    if not path.exists():
        return {"name": label, "status": "OK", "message": "missing-allowed"}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"name": label, "status": "BLOCKER", "message": "invalid-json", "details": {"error": str(exc)}}
    if not isinstance(payload, expected_type):
        return {
            "name": label,
            "status": "BLOCKER",
            "message": "unexpected-type",
            "details": {"expected": expected_type.__name__, "actual": type(payload).__name__},
        }
    size = len(payload) if hasattr(payload, "__len__") else None
    return {"name": label, "status": "OK", "message": "readable", "details": {"entries": size}}


def _check_directory_writable(path: Path, label: str) -> dict:
    if not path.exists():
        return {"name": label, "status": "BLOCKER", "message": "missing-directory", "details": {"path": str(path)}}
    if not path.is_dir():
        return {"name": label, "status": "BLOCKER", "message": "not-a-directory", "details": {"path": str(path)}}
    try:
        probe = path / ".ptbrmerger-preflight.tmp"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return {"name": label, "status": "OK", "message": "writable", "details": {"path": str(path)}}
    except OSError as exc:
        return {"name": label, "status": "BLOCKER", "message": "not-writable", "details": {"path": str(path), "error": str(exc)}}


def _check_radarr(cfg) -> dict:
    try:
        response = requests.get(
            cfg.radarr.url.rstrip("/") + "/api/v3/system/status",
            headers={"X-Api-Key": cfg.radarr.api_key},
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json() if response.text else {}
        return {
            "name": "radarr",
            "status": "OK",
            "message": "reachable",
            "details": {"version": payload.get("version")},
        }
    except Exception as exc:
        return {"name": "radarr", "status": "BLOCKER", "message": "unreachable", "details": {"error": str(exc)}}


def _check_qbittorrent() -> dict:
    session = qbit_login()
    if not session:
        return {"name": "qbittorrent", "status": "BLOCKER", "message": "login-failed"}
    return {"name": "qbittorrent", "status": "OK", "message": "reachable"}


def _check_bazarr(cfg) -> dict:
    base_url = str(getattr(cfg.bazarr, "url", "") or "").strip()
    api_key = str(getattr(cfg.bazarr, "api_key", "") or "").strip()
    if not base_url or not api_key:
        return {"name": "bazarr", "status": "WARN", "message": "disabled-or-missing-config"}
    try:
        response = requests.get(
            base_url.rstrip("/") + "/api/system/status",
            headers={"X-API-KEY": api_key},
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json() if response.text else {}
        return {"name": "bazarr", "status": "OK", "message": "reachable", "details": {"version": payload.get("version")}}
    except Exception as exc:
        return {"name": "bazarr", "status": "WARN", "message": "request-failed", "details": {"error": str(exc)}}


def _check_discord(cfg) -> dict:
    webhook_url = str(getattr(cfg.notifications, "discord_webhook_url", "") or "").strip()
    if not webhook_url:
        return {"name": "discord", "status": "WARN", "message": "disabled"}
    return {"name": "discord", "status": "OK", "message": "configured-not-probed"}


def run_preflight(base_dir: Path | None = None) -> dict:
    cfg = get_config()
    root = Path(base_dir) if base_dir is not None else Path(__file__).resolve().parents[2]

    checks = [
        _check_executable(cfg.ffmpeg.ffmpeg_path, "ffmpeg"),
        _check_executable(cfg.ffmpeg.ffprobe_path, "ffprobe"),
        _check_directory_writable(Path(cfg.radarr.ptbrmerger_root_folder), "ptbrmerger_root_folder"),
        _check_json_file(root / cfg.processing.queue_file, dict, "queue.json"),
        _check_json_file(root / cfg.retry.queue_file, dict, "retry_queue.json"),
        _check_json_file(root / cfg.logging.history_file, list, "history.json"),
        _check_json_file(root / cfg.logging.group_history_file, list, "group_history.json"),
        _check_radarr(cfg),
        _check_qbittorrent(),
        _check_bazarr(cfg),
        _check_discord(cfg),
    ]

    statuses = {check["status"] for check in checks}
    overall = "BLOCKER" if "BLOCKER" in statuses else "WARN" if "WARN" in statuses else "OK"
    return {"status": overall, "checks": checks}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Preflight operacional do PTBRMerger.")
    parser.add_argument("--json", action="store_true", help="Imprime apenas o payload JSON.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = run_preflight()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    print(f"Overall: {report['status']}")
    print(json.dumps(report["checks"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
