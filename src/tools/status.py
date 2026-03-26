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


def _build_manual_recovery_snapshot(queue_payload: dict, history_payload: list[dict]) -> list[dict]:
    manual_entries: list[dict] = []
    seen_tmdb_ids: set[str] = set()

    for tmdb_id, entry in (queue_payload or {}).items():
        if not isinstance(entry, dict):
            continue
        if not (
            entry.get("manual_recovery")
            or entry.get("manual_request_id")
            or str(entry.get("phase") or "") == "manual-recovery"
            or str(entry.get("status") or "").startswith("MANUAL_RECOVERY")
        ):
            continue
        manual_entries.append(
            {
                "tmdbId": str(entry.get("tmdbId") or tmdb_id),
                "status": entry.get("status"),
                "phase": entry.get("phase"),
                "manual_request_id": entry.get("manual_request_id"),
                "manual_candidate_index": entry.get("manual_candidate_index"),
                "manual_force_offset_seconds": entry.get("manual_force_offset_seconds"),
                "manual_trim_start_seconds": entry.get("manual_trim_start_seconds"),
                "manual_trim_end_seconds": entry.get("manual_trim_end_seconds"),
                "manual_reuse_last_recovery": entry.get("manual_reuse_last_recovery"),
                "manual_preserve_artifacts": entry.get("manual_preserve_artifacts"),
                "manual_source_path": entry.get("manual_source_path"),
            }
        )
        seen_tmdb_ids.add(str(entry.get("tmdbId") or tmdb_id))

    for event in history_payload or []:
        if not isinstance(event, dict):
            continue
        tmdb_id = str(event.get("tmdbId") or "")
        if tmdb_id in seen_tmdb_ids:
            continue
        if not (event.get("manual_recovery") or str(event.get("status") or "").startswith("MANUAL_RECOVERY")):
            continue
        manual_entries.append(
            {
                "tmdbId": tmdb_id,
                "status": event.get("status"),
                "phase": event.get("phase"),
                "manual_request_id": event.get("manual_request_id"),
                "manual_candidate_index": event.get("manual_candidate_index"),
                "manual_force_offset_seconds": event.get("manual_force_offset_seconds"),
                "manual_trim_start_seconds": event.get("manual_trim_start_seconds"),
                "manual_trim_end_seconds": event.get("manual_trim_end_seconds"),
                "manual_reuse_last_recovery": event.get("manual_reuse_last_recovery"),
                "manual_preserve_artifacts": event.get("manual_preserve_artifacts"),
                "manual_source_path": event.get("manual_source_path"),
            }
        )

    return manual_entries


def build_status_snapshot(
    queue_file: Path,
    history_file: Path,
    torrent_rows: list[dict] | None = None,
    group_history_file: Path | None = None,
    retry_queue_file: Path | None = None,
) -> dict:
    queue_payload = _safe_load_json(Path(queue_file), {})
    history_payload = _safe_load_json(Path(history_file), [])
    retry_payload = _safe_load_json(Path(retry_queue_file), {}) if retry_queue_file is not None else {}
    compatibility_summary = {}
    if group_history_file is not None:
        compatibility_summary = GroupHistoryManager(Path(group_history_file)).summarize()
    manual_recoveries = _build_manual_recovery_snapshot(
        queue_payload if isinstance(queue_payload, dict) else {},
        history_payload if isinstance(history_payload, list) else [],
    )
    return {
        "queue": queue_payload if isinstance(queue_payload, dict) else {},
        "retry_queue": retry_payload if isinstance(retry_payload, dict) else {},
        "history": history_payload if isinstance(history_payload, list) else [],
        "torrents": list(torrent_rows or []),
        "compatibility": compatibility_summary,
        "manual_recoveries": manual_recoveries,
    }


def parse_args() -> argparse.Namespace:
    config = get_config()
    parser = argparse.ArgumentParser(description="Resumo operacional do PTBRMerger.")
    parser.add_argument("--queue-file", default=config.processing.queue_file, help="Arquivo queue.json")
    parser.add_argument("--retry-queue-file", default=config.retry.queue_file, help="Arquivo retry_queue.json")
    parser.add_argument("--history-file", default=config.logging.history_file, help="Arquivo history.json")
    parser.add_argument("--group-history-file", default=config.logging.group_history_file, help="Arquivo group_history.json")
    parser.add_argument("--history-limit", type=int, default=10, help="Quantidade de eventos recentes")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    snapshot = build_status_snapshot(
        queue_file=Path(args.queue_file),
        retry_queue_file=Path(args.retry_queue_file),
        history_file=Path(args.history_file),
        torrent_rows=list_ptbr_torrents(),
        group_history_file=Path(args.group_history_file),
    )
    print("Queue:")
    print(json.dumps(snapshot["queue"], ensure_ascii=False, indent=2))
    print()
    print("Retry Queue:")
    print(json.dumps(snapshot["retry_queue"], ensure_ascii=False, indent=2))
    print()
    print("History:")
    print(json.dumps(snapshot["history"][-args.history_limit :], ensure_ascii=False, indent=2))
    print()
    print("Torrents:")
    print(json.dumps(snapshot["torrents"], ensure_ascii=False, indent=2))
    print()
    print("Compatibility:")
    print(json.dumps(snapshot["compatibility"], ensure_ascii=False, indent=2))
    print()
    print("Manual Recoveries:")
    print(json.dumps(snapshot["manual_recoveries"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
