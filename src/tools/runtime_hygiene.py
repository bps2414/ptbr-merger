import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import shutil

from src.config import get_config


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _empty_payload_for(path: Path):
    name = path.name.lower()
    if name in {"queue.json", "retry_queue.json"}:
        return {}
    if name in {"history.json", "group_history.json"}:
        return []
    return ""


def build_runtime_hygiene_plan(targets: list[Path], archive_root: Path) -> dict:
    files = []
    for target in targets:
        exists = target.exists()
        size = target.stat().st_size if exists and target.is_file() else 0
        files.append(
            {
                "path": str(target),
                "exists": exists,
                "size_bytes": size,
                "reset_to": type(_empty_payload_for(target)).__name__,
            }
        )
    return {
        "archive_root": str(archive_root),
        "files": files,
    }


def apply_runtime_hygiene(targets: list[Path], archive_root: Path) -> dict:
    archive_dir = archive_root / f"runtime-{_utc_stamp()}"
    archive_dir.mkdir(parents=True, exist_ok=True)
    results = []

    for target in targets:
        entry = {"path": str(target), "archived": False, "reset": False}
        if target.exists():
            archived_path = archive_dir / target.name
            shutil.copy2(target, archived_path)
            entry["archived"] = True
            entry["archive_path"] = str(archived_path)

        empty_payload = _empty_payload_for(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(empty_payload, (dict, list)):
            target.write_text(json.dumps(empty_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            target.write_text(str(empty_payload), encoding="utf-8")
        entry["reset"] = True
        results.append(entry)

    return {"archive_dir": str(archive_dir), "results": results}


def _default_targets(root: Path, cfg) -> list[Path]:
    targets = [
        root / cfg.processing.queue_file,
        root / cfg.retry.queue_file,
        root / cfg.logging.history_file,
        root / cfg.logging.group_history_file,
    ]
    log_file = str(getattr(cfg.logging, "file", "") or "").strip()
    if log_file:
        targets.append(root / log_file)
    return targets


def parse_args() -> argparse.Namespace:
    cfg = get_config()
    parser = argparse.ArgumentParser(description="Archive e reset seguro do estado runtime do PTBRMerger.")
    parser.add_argument("--apply", action="store_true", help="Aplica archive + reset. Sem esta flag, roda em dry-run.")
    parser.add_argument("--archive-root", default=".runtime-archive", help="Diretório raiz para arquivamento.")
    parser.add_argument("--json", action="store_true", help="Imprime apenas JSON.")
    parser.add_argument(
        "--targets",
        nargs="*",
        default=None,
        help="Lista opcional de arquivos para higienizar. Default: queue/history/group_history/retry/log.",
    )
    parser.set_defaults(_config=cfg)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = Path(__file__).resolve().parents[2]
    cfg = args._config
    targets = [Path(path) for path in args.targets] if args.targets else _default_targets(root, cfg)
    archive_root = Path(args.archive_root)

    if args.apply:
        payload = apply_runtime_hygiene(targets, archive_root)
    else:
        payload = build_runtime_hygiene_plan(targets, archive_root)

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
