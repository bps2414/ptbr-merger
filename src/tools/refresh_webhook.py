import argparse
from pathlib import Path

import src.qbit_client as qbit_client
import src.radarr_client as radarr_client
from src.config import get_config
from src.history_manager import HistoryManager
from src.notifier import info, send_progress_update, warning
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
        if entry.get("status") in {"SUCCESS", "ABANDONED"}:
            continue

        current_tmdb = str(entry.get("tmdbId"))
        movie = radarr_client.get_movie_by_tmdbid(current_tmdb)
        torrent = _find_torrent_for_tmdb(torrent_rows, current_tmdb)
        phase, context = build_refresh_payload(entry, movie, history_events, torrent)
        message_id = send_progress_update(phase=phase, context=context, message_id=context.get("discord_message_id"))
        if message_id:
            queue_manager.attach_metadata(current_tmdb, discord_message_id=message_id)
            updated += 1
            info(f"Webhook atualizado para TMDB {current_tmdb} na fase {phase}.")
        else:
            warning(f"Falha ao atualizar webhook para TMDB {current_tmdb}.")

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
