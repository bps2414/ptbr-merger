import argparse
import json
from pathlib import Path

from src.config import get_config
from src.qbit_client import list_ptbr_torrents
from src.sync_intelligence import GroupHistoryManager


def _safe_load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def build_status_snapshot(
    queue_file: Path,
    history_file: Path,
    torrent_rows: list[dict] | None = None,
    group_history_file: Path | None = None,
) -> dict:
    queue_payload = _safe_load_json(Path(queue_file), {})
    history_payload = _safe_load_json(Path(history_file), [])
    compatibility_summary = {}
    if group_history_file is not None:
        compatibility_summary = GroupHistoryManager(Path(group_history_file)).summarize()
    return {
        "queue": queue_payload if isinstance(queue_payload, dict) else {},
        "history": history_payload if isinstance(history_payload, list) else [],
        "torrents": list(torrent_rows or []),
        "compatibility": compatibility_summary,
    }


def parse_args() -> argparse.Namespace:
    config = get_config()
    parser = argparse.ArgumentParser(description="Resumo operacional do PTBRMerger.")
    parser.add_argument("--queue-file", default=config.processing.queue_file, help="Arquivo queue.json")
    parser.add_argument("--history-file", default=config.logging.history_file, help="Arquivo history.json")
    parser.add_argument("--group-history-file", default=config.logging.group_history_file, help="Arquivo group_history.json")
    parser.add_argument("--history-limit", type=int, default=10, help="Quantidade de eventos recentes")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    snapshot = build_status_snapshot(
        queue_file=Path(args.queue_file),
        history_file=Path(args.history_file),
        torrent_rows=list_ptbr_torrents(),
        group_history_file=Path(args.group_history_file),
    )
    print("Queue:")
    print(json.dumps(snapshot["queue"], ensure_ascii=False, indent=2))
    print()
    print("History:")
    print(json.dumps(snapshot["history"][-args.history_limit :], ensure_ascii=False, indent=2))
    print()
    print("Torrents:")
    print(json.dumps(snapshot["torrents"], ensure_ascii=False, indent=2))
    print()
    print("Compatibility:")
    print(json.dumps(snapshot["compatibility"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
