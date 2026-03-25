from urllib.parse import urljoin

import requests

from src.config import get_config
from src.notifier import debug, warning

config = get_config()


def _matches_requested_language(subtitle_row, language: str) -> bool:
    language_lower = str(language or "").lower()
    raw = str(subtitle_row).lower()
    if language_lower and language_lower in raw:
        return True
    if language_lower.startswith("pt") and any(
        token in raw for token in ("pt-br", "portuguese", "português", "'pt'", '"pt"', " pt ")
    ):
        return True
    return False


def lookup_ptbr_subtitles(tmdb_id: str, title: str = "", year: str = "") -> dict:
    bazarr_url = str(getattr(config.bazarr, "url", "") or "").strip()
    bazarr_api_key = str(getattr(config.bazarr, "api_key", "") or "").strip()
    language = str(getattr(config.bazarr, "language", "pt-BR") or "pt-BR")

    if not bazarr_url or not bazarr_api_key:
        return {
            "configured": False,
            "available": False,
            "reason": "disabled",
            "language": language,
        }

    headers = {"X-API-KEY": bazarr_api_key}
    try:
        response = requests.get(
            urljoin(bazarr_url, "/api/movies"),
            headers=headers,
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json() or []
    except Exception as exc:
        warning(f"Falha consultando Bazarr para {title or tmdb_id}: {exc}")
        return {
            "configured": True,
            "available": False,
            "reason": "request-failed",
            "language": language,
        }

    if isinstance(payload, dict):
        rows = payload.get("data") or payload.get("movies") or []
    else:
        rows = payload

    normalized_tmdb = str(tmdb_id)
    normalized_title = str(title or "").lower()
    candidates = []
    for row in rows if isinstance(rows, list) else []:
        row_tmdb = str(row.get("tmdbId") or row.get("tmdbid") or "")
        row_title = str(row.get("title") or row.get("sceneName") or "").lower()
        if row_tmdb == normalized_tmdb or (normalized_title and normalized_title in row_title):
            candidates.append(row)

    if not candidates:
        debug(f"Bazarr não retornou item correspondente para TMDB {tmdb_id}.")
        return {
            "configured": True,
            "available": False,
            "reason": "movie-not-found",
            "language": language,
        }

    subtitle_count = 0
    for row in candidates:
        subtitles = row.get("subtitles") or []
        subtitle_count += len([sub for sub in subtitles if _matches_requested_language(sub, language)])

    return {
        "configured": True,
        "available": subtitle_count > 0,
        "reason": "subtitle-found" if subtitle_count > 0 else "subtitle-not-found",
        "language": language,
        "subtitle_count": subtitle_count,
    }
