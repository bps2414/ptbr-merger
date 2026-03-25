import argparse
from pathlib import Path

import src.qbit_client as qbit_client
import src.radarr_client as radarr_client
from src.config import get_config
from src.history_manager import HistoryManager
from src.notifier import info, notify_status, send_progress_update, warning
from src.queue_manager import QueueManager

config = get_config()
BASE_DIR = Path(__file__).resolve().parents[2]


def _extract_image_url(movie: dict | None, cover_type: str) -> str | None:
    if not movie:
        return None
    for image in movie.get("images", []) or []:
        if image.get("coverType") != cover_type:
            continue
        for key in ("remoteUrl", "url"):
            value = image.get(key)
            if value:
                return value
    return None


def _phase_for_queue_entry(entry: dict, torrent: dict | None) -> str:
    phase = str(entry.get("phase", "") or "")
    if phase == "await-download":
        return "download-await"
    if phase in {"merge", "extract", "mux", "validate", "finalize", "search", "inject", "download-await", "merge-start"}:
        return phase
    if torrent and float(torrent.get("progress", 0) or 0) < 100.0:
        return "download-await"
    return "search"


def _latest_event(events: list[dict], tmdb_id: str) -> dict:
    for event in reversed(events):
        if str(event.get("tmdbId")) == str(tmdb_id):
            return event
    return {}


def _find_torrent_for_tmdb(torrent_rows: list[dict], tmdb_id: str) -> dict | None:
    tag = f"ptbrmerger-tmdbid-{tmdb_id}"
    for row in torrent_rows:
        if tag in str(row.get("tags", "")):
            return row
    return None


def build_refresh_payload(entry: dict, movie: dict | None, events: list[dict], torrent: dict | None) -> tuple[str, dict]:
    tmdb_id = str(entry.get("tmdbId") or "")
    latest = _latest_event(events, tmdb_id)
    context = {
        "tmdbId": tmdb_id,
        "title": (movie or {}).get("title") or latest.get("title") or f"TMDB_{tmdb_id}",
        "year": str((movie or {}).get("year") or latest.get("year") or ""),
        "candidate_index": entry.get("candidate_index", latest.get("candidate_index")),
        "discord_message_id": entry.get("discord_message_id"),
        "release_title": latest.get("release_title"),
        "indexer": latest.get("indexer"),
        "score": latest.get("score"),
        "diff": latest.get("sync_diff"),
        "offset_estimate": latest.get("offset_estimate"),
        "process_runtime": latest.get("process_runtime"),
        "group": latest.get("group"),
        "source_4k": latest.get("source_4k"),
        "source_1080p": latest.get("source_1080p"),
        "history_bonus": latest.get("history_bonus"),
        "history_reason": latest.get("history_reason"),
        "offset_applied": latest.get("offset_applied"),
        "offset_applied_seconds": latest.get("offset_applied_seconds"),
        "offset_outcome": latest.get("offset_outcome"),
        "fingerprint_category": latest.get("fingerprint_category"),
        "fingerprint_confidence": latest.get("fingerprint_confidence"),
        "fingerprint_offset": latest.get("fingerprint_offset"),
        "offset_strategy": latest.get("offset_strategy"),
    }

    poster_url = _extract_image_url(movie, "poster")
    backdrop_url = _extract_image_url(movie, "fanart")
    if poster_url:
        context["poster_url"] = poster_url
    if backdrop_url:
        context["backdrop_url"] = backdrop_url

    if torrent:
        progress = torrent.get("progress")
        if progress is not None:
            context["progress_percent"] = int(round(float(progress)))
        if torrent.get("eta") not in (None, -1):
            context["eta_seconds"] = torrent.get("eta")
        if torrent.get("state"):
            context["qbit_state"] = torrent.get("state")
        if torrent.get("num_seeds") is not None:
            context["num_seeds"] = torrent.get("num_seeds")
        if torrent.get("num_leechs") is not None:
            context["num_leechs"] = torrent.get("num_leechs")

    return _phase_for_queue_entry(entry, torrent), context


def _status_for_entry(entry: dict, events: list[dict], tmdb_id: str) -> str:
    latest = _latest_event(events, tmdb_id)
    latest_status = str(latest.get("status") or "")
    if latest_status:
        return latest_status
    status = str(entry.get("status") or "")
    if status == "SUCCESS":
        return "SUCCESS"
    if status == "ABANDONED":
        return "ABANDONED"
    return "PROGRESS"


def _context_from_history_only(tmdb_id: str, movie: dict | None, events: list[dict]) -> tuple[str, dict] | None:
    latest = _latest_event(events, tmdb_id)
    status = str(latest.get("status") or "")
    if not status:
        return None

    context = {
        "tmdbId": tmdb_id,
        "title": (movie or {}).get("title") or latest.get("title") or f"TMDB_{tmdb_id}",
        "year": str((movie or {}).get("year") or latest.get("year") or ""),
        "candidate_index": latest.get("candidate_index"),
        "release_title": latest.get("release_title"),
        "indexer": latest.get("indexer"),
        "score": latest.get("score"),
        "diff": latest.get("sync_diff"),
        "offset_estimate": latest.get("offset_estimate"),
        "process_runtime": latest.get("process_runtime"),
        "group": latest.get("group"),
        "source_4k": latest.get("source_4k"),
        "source_1080p": latest.get("source_1080p"),
        "history_bonus": latest.get("history_bonus"),
        "history_reason": latest.get("history_reason"),
        "offset_applied": latest.get("offset_applied"),
        "offset_applied_seconds": latest.get("offset_applied_seconds"),
        "offset_outcome": latest.get("offset_outcome"),
        "fingerprint_category": latest.get("fingerprint_category"),
        "fingerprint_confidence": latest.get("fingerprint_confidence"),
        "fingerprint_offset": latest.get("fingerprint_offset"),
        "offset_strategy": latest.get("offset_strategy"),
    }

    poster_url = _extract_image_url(movie, "poster")
    backdrop_url = _extract_image_url(movie, "fanart")
    if poster_url:
        context["poster_url"] = poster_url
    if backdrop_url:
        context["backdrop_url"] = backdrop_url

    return status, context


def refresh_webhooks(tmdb_id: str | None = None) -> int:
    queue_manager = QueueManager(BASE_DIR / config.processing.queue_file, max_attempts=config.processing.max_attempts)
    history_manager = HistoryManager(
        BASE_DIR / config.logging.history_file,
        max_entries=getattr(config.logging, "history_max_entries", 500),
    )

    queue_payload = queue_manager._read()
    history_events = history_manager._read()
    torrent_rows = qbit_client.list_ptbr_torrents()

    updated = 0
    for entry in queue_payload.values():
        if tmdb_id and str(entry.get("tmdbId")) != str(tmdb_id):
            continue
        if not entry.get("discord_message_id"):
            continue
        current_tmdb = str(entry.get("tmdbId"))
        movie = radarr_client.get_movie_by_tmdbid(current_tmdb)
        torrent = _find_torrent_for_tmdb(torrent_rows, current_tmdb)
        phase, context = build_refresh_payload(entry, movie, history_events, torrent)
        status = _status_for_entry(entry, history_events, current_tmdb)

        if status == "PROGRESS":
            message_id = send_progress_update(phase=phase, context=context, message_id=context.get("discord_message_id"))
        else:
            notify_status(status, context)
            message_id = context.get("discord_message_id")
        if message_id:
            queue_manager.attach_metadata(current_tmdb, discord_message_id=message_id)
            updated += 1
            info(f"Webhook atualizado para TMDB {current_tmdb} na fase {phase}.")
        else:
            warning(f"Falha ao atualizar webhook para TMDB {current_tmdb}.")

    if tmdb_id and updated == 0:
        current_tmdb = str(tmdb_id)
        movie = radarr_client.get_movie_by_tmdbid(current_tmdb)
        history_only = _context_from_history_only(current_tmdb, movie, history_events)
        if history_only:
            status, context = history_only
            notify_status(status, context)
            message_id = context.get("discord_message_id")
            if message_id:
                status_phase = "analyzer" if status == "SKIPPED_HAS_PTBR" else "refresh"
                existing_entry = queue_manager.get_entry(current_tmdb)
                if existing_entry:
                    queue_manager.attach_metadata(current_tmdb, discord_message_id=message_id)
                else:
                    if status in {"SUCCESS", "SKIPPED_HAS_PTBR"}:
                        queue_manager.record_success(current_tmdb, status_phase, candidate_index=0)
                    elif status == "ABANDONED":
                        queue_manager.record_failure(current_tmdb, status_phase, "refresh_terminal_status", candidate_index=0)
                    else:
                        queue_manager.record_pending(current_tmdb, status_phase, candidate_index=0)
                    queue_manager.attach_metadata(current_tmdb, discord_message_id=message_id)
                updated += 1
                info(f"Webhook terminal recriado para TMDB {current_tmdb} com base no histórico.")

    return updated


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Atualiza imediatamente o webhook do Discord com o estado atual.")
    parser.add_argument("--tmdb", help="Atualiza apenas o filme informado pelo TMDB ID.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    updated = refresh_webhooks(tmdb_id=args.tmdb)
    print(f"webhooks_updated={updated}")


if __name__ == "__main__":
    main()
