import time
from enum import Enum
from pathlib import Path
from typing import List, Optional, Tuple
from urllib.parse import urljoin

import requests

from src.config import get_config
from src.notifier import debug, error, info

config = get_config()


class MergerState(Enum):
    NEW_MOVIE = 1
    WAITING_DOWNLOAD = 2
    RESUME_FROM_MUX = 3


_API_KEY = config.radarr.api_key
_BASE_URL = config.radarr.url
_HEADERS = {"X-Api-Key": _API_KEY}
_PROFILE_ID_CACHE = {}
_TAG_ID_CACHE = {}
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


def _get_timeout() -> int:
    return getattr(config.radarr, "timeout", 10)


def exponential_backoff(func):
    def wrapper(*args, **kwargs):
        delays = [0, 1, 2, 4, 8]
        last_error = None

        for attempt, delay in enumerate(delays, start=1):
            if delay:
                time.sleep(delay)

            try:
                return func(*args, **kwargs)
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
                last_error = exc
                if attempt == len(delays):
                    raise
            except requests.exceptions.HTTPError as exc:
                last_error = exc
                status_code = getattr(exc.response, "status_code", None)
                if status_code not in _RETRYABLE_STATUS_CODES or attempt == len(delays):
                    raise

        if last_error:
            raise last_error
        return None

    return wrapper


@exponential_backoff
def _request(method: str, endpoint: str, **kwargs):
    url = urljoin(_BASE_URL, endpoint)
    kwargs.setdefault("timeout", _get_timeout())
    kwargs.setdefault("headers", _HEADERS)

    try:
        response = requests.request(method, url, **kwargs)
        response.raise_for_status()
        if response.text and response.status_code != 204:
            return response.json()
        return response
    except requests.exceptions.HTTPError as exc:
        err_msg = exc.response.text if exc.response is not None else ""
        error(f"Erro de comunicação API Radarr ({method} {endpoint}): {exc} - Body: {err_msg}")
        raise
    except requests.exceptions.RequestException as exc:
        error(f"Erro de comunicação de rede API Radarr ({method} {endpoint}): {exc}")
        raise


def get_profile_id(profile_name: str) -> int:
    if profile_name in _PROFILE_ID_CACHE:
        return _PROFILE_ID_CACHE[profile_name]
    profiles = _request("GET", "/api/v3/qualityprofile")
    for profile in profiles:
        if profile.get("name") == profile_name:
            profile_id = profile.get("id")
            _PROFILE_ID_CACHE[profile_name] = profile_id
            return profile_id
    raise ValueError(f"Profile '{profile_name}' não encontrado no Radarr.")


def get_tag_id(tag_name: str) -> int:
    if tag_name in _TAG_ID_CACHE:
        return _TAG_ID_CACHE[tag_name]
    tags = _request("GET", "/api/v3/tag")
    for tag in tags:
        if tag.get("label") == tag_name:
            tag_id = tag.get("id")
            _TAG_ID_CACHE[tag_name] = tag_id
            return tag_id
    raise ValueError(f"Tag '{tag_name}' não encontrada no Radarr.")


def ensure_tag_id(tag_name: str) -> int:
    try:
        return get_tag_id(tag_name)
    except ValueError:
        created = _request("POST", "/api/v3/tag", json={"label": tag_name})
        tag_id = created.get("id")
        _TAG_ID_CACHE[tag_name] = tag_id
        return tag_id


def apply_success_tag(movie_id: int) -> None:
    tag_id = ensure_tag_id(getattr(config.radarr, "success_tag_label", "ptbr-merged"))
    _request(
        "PUT",
        "/api/v3/movie/editor",
        json={
            "movieIds": [movie_id],
            "tags": [tag_id],
            "applyTags": "add",
        },
    )
    info(f"Tag de sucesso aplicada ao filme ID {movie_id}.")


def get_movie_by_tmdbid(tmdb_id: str) -> Optional[dict]:
    movies = _request("GET", f"/api/v3/movie?tmdbId={tmdb_id}")
    if isinstance(movies, list) and movies:
        return movies[0]
    return None


def arquivo_existe_em_temp(tmdb_id: str) -> Optional[Path]:
    temp_folder = Path(config.radarr.ptbrmerger_root_folder)
    if not temp_folder.exists() or not temp_folder.is_dir():
        return None
    mkv_files = list(temp_folder.rglob("*.mkv"))
    if mkv_files:
        return mkv_files[0]
    return None


def _is_blacklisted(title: str) -> bool:
    import re

    blacklist = getattr(config.ptbr_keywords, "blacklist", [])
    title_lower = title.lower()
    for word in blacklist:
        if len(word) <= 3:
            if re.search(rf"\b{re.escape(word.lower())}\b", title_lower):
                return True
        else:
            if word.lower() in title_lower:
                return True
    return False


def _is_blocked_quality(quality_name: str) -> bool:
    blocked = ["2160p", "4K", "TELECINE", "CAM", "TELESYNC", "HDCAM", "HDTV"]
    quality_upper = quality_name.upper()
    return any(blocked_name.upper() in quality_upper for blocked_name in blocked)


def _calculate_tiebreaker(release: dict, original_cut_keywords: List[str]) -> Tuple[int, str]:
    import re

    title = release.get("title", "")
    title_lower = title.lower()
    title_upper = title.upper()
    indexer_name = release.get("indexer", "")
    quality_name = release.get("quality", {}).get("quality", {}).get("name", "")

    score = 0
    matched_keywords = []

    for keyword in getattr(config.ptbr_keywords, "high_priority", []):
        if keyword.lower() in title_lower:
            score += 8
            matched_keywords.append(f"[L4]{keyword}")

    for br_indexer in getattr(config.ptbr_keywords, "indexer_names_br", []):
        if br_indexer.lower() in indexer_name.lower():
            score += 4
            matched_keywords.append(f"[L3]indexer:{br_indexer}")
            break

    for keyword in getattr(config.ptbr_keywords, "medium_priority", []):
        if len(keyword) <= 3:
            if re.search(rf"\b{re.escape(keyword.lower())}\b", title_lower):
                score += 2
                matched_keywords.append(f"[L2]{keyword}")
        elif keyword.lower() in title_lower:
            score += 2
            matched_keywords.append(f"[L2]{keyword}")

    if "WEBDL" in quality_name.upper() or "WEB-DL" in quality_name.upper():
        score += 1
        matched_keywords.append("[L1]WEBDL")

    cut_keywords_list = ["REPACK", "EXTENDED", "THEATRICAL", "IMAX", "DIRECTORS.CUT", "UNRATED"]
    candidate_cut_keywords = [keyword for keyword in cut_keywords_list if keyword in title_upper]

    for keyword in cut_keywords_list:
        has_in_4k = keyword in original_cut_keywords
        has_in_1080p = keyword in candidate_cut_keywords

        if has_in_4k and has_in_1080p:
            score += 5
            matched_keywords.append(f"[+5]{keyword}")
        elif has_in_4k and not has_in_1080p:
            score -= 10
            matched_keywords.append(f"[-10]Falta {keyword}")
        elif not has_in_4k and has_in_1080p:
            score -= 10
            matched_keywords.append(f"[-10]Sobra {keyword}")

    if matched_keywords:
        return score, f"Tiebreaker {score} (Keywords: {', '.join(matched_keywords)})"
    return score, f"Tiebreaker {score}"


def find_best_ptbr_release(tmdb_id: str, exclude_titles: Optional[List[str]] = None) -> List[dict]:
    exclude_titles = exclude_titles or []
    min_score = getattr(config.radarr, "ptbrmerger_min_score", 10000)

    movie = get_movie_by_tmdbid(tmdb_id)
    if not movie:
        error(f"Filme TMDB {tmdb_id} não encontrado na base do Radarr.")
        return []

    file_4k_name = ""
    if "movieFile" in movie and movie["movieFile"]:
        file_4k_name = movie["movieFile"].get("path", "")
    elif "path" in movie:
        folder = Path(movie["path"])
        if folder.exists() and folder.is_dir():
            mkv_files = list(folder.rglob("*.mkv"))
            if mkv_files:
                file_4k_name = max(mkv_files, key=lambda path: path.stat().st_size).name

    cut_keywords_list = ["REPACK", "EXTENDED", "THEATRICAL", "IMAX", "DIRECTORS.CUT", "UNRATED"]
    original_cut_keywords = []
    if file_4k_name:
        file_4k_name_upper = Path(file_4k_name).name.upper()
        for keyword in cut_keywords_list:
            if keyword in file_4k_name_upper:
                original_cut_keywords.append(keyword)

    if original_cut_keywords:
        info(f"Cortes detectados no arquivo 4K original: {original_cut_keywords}")
    else:
        debug("Nenhum corte especial (REPACK, EXTENDED, etc) detectado no arquivo original.")

    movie_id = movie["id"]
    info(f"Buscando releases para o filme ID {movie_id} no Radarr (pode demorar até 60s)...")

    try:
        releases = _request("GET", f"/api/v3/release?movieId={movie_id}", timeout=120)
    except Exception as exc:
        error(f"Falha na busca interativa de releases: {exc}")
        return []

    if not releases:
        debug("Busca retornou zero releases.")
        return []

    all_scores = sorted([release.get("customFormatScore", 0) for release in releases], reverse=True)
    info(f"Busca retornou {len(releases)} releases. Top 5 scores: {all_scores[:5]}")

    candidates = []

    for release in releases:
        cf_score = release.get("customFormatScore", 0)
        title = release.get("title", "")
        quality_name = release.get("quality", {}).get("quality", {}).get("name", "")
        url = release.get("downloadUrl") or release.get("magnetUrl")

        if cf_score < min_score or not url:
            continue
        if title in exclude_titles:
            debug(f"Release excluída (já tentada): {title}")
            continue
        if _is_blacklisted(title):
            debug(f"Release rejeitada pela blacklist: {title}")
            continue
        if _is_blocked_quality(quality_name):
            debug(f"Release rejeitada pela qualidade: {title} [{quality_name}]")
            continue

        tiebreaker_score, justificativa = _calculate_tiebreaker(release, original_cut_keywords)
        info(f"Release detectada [Score {cf_score}][{quality_name}]: {title} | Tiebreaker: {tiebreaker_score}")

        candidates.append(
            {
                "title": title,
                "url": url,
                "cf_score": cf_score,
                "tiebreaker_score": tiebreaker_score,
                "justificativa": justificativa,
                "quality": quality_name,
                "size": release.get("size", 0),
                "indexer": release.get("indexer", ""),
                "downloadUrl": release.get("downloadUrl"),
                "magnetUrl": release.get("magnetUrl"),
            }
        )

    if not candidates:
        debug(f"Nenhum release elegível encontrado (min_score={min_score}).")
        return []

    candidates.sort(
        key=lambda candidate: (
            candidate["tiebreaker_score"],
            1 if "WEBDL" in candidate["quality"].upper() or "WEB-DL" in candidate["quality"].upper() else 0,
            -candidate["size"],
        ),
        reverse=True,
    )

    for index, candidate in enumerate(candidates[:5], 1):
        info(
            f"Candidato #{index} [Tiebreaker {candidate['tiebreaker_score']}][{candidate['quality']}]: "
            f"{candidate['title']} ({candidate['justificativa']})"
        )

    return candidates[:5]


def add_movie_ptbrmerger(tmdb_id: str, title: str, year: str) -> Tuple[int, MergerState]:
    ptbrmerger_profile_id = get_profile_id(config.radarr.ptbrmerger_profile_name)
    ptbrmerger_tag_id = get_tag_id(config.radarr.ptbrmerger_tag_name)

    existing = get_movie_by_tmdbid(tmdb_id)
    if existing and existing.get("qualityProfileId") == ptbrmerger_profile_id:
        movie_id = existing.get("id")
        info(f"{title} já está no perfil PTBRMerger. Verificando estado...")
        if arquivo_existe_em_temp(tmdb_id):
            debug("RESUME_FROM_MUX: arquivo existe na pasta temp.")
            return movie_id, MergerState.RESUME_FROM_MUX
        debug("WAITING_DOWNLOAD: aguardando Radarr baixar.")
        return movie_id, MergerState.WAITING_DOWNLOAD

    payload = {
        "tmdbId": int(tmdb_id),
        "title": title,
        "year": int(year) if year else 0,
        "qualityProfileId": ptbrmerger_profile_id,
        "rootFolderPath": config.radarr.ptbrmerger_root_folder,
        "monitored": True,
        "tags": [ptbrmerger_tag_id],
        "addOptions": {"searchForMovie": True},
    }

    debug(f"Adicionando {title} ({year}) no perfil PTBRMerger...")
    response = _request("POST", "/api/v3/movie", json=payload)
    return response.get("id"), MergerState.NEW_MOVIE


def remove_movie_ptbrmerger(movie_id: int) -> None:
    debug(f"Removendo filme ID {movie_id} do perfil PTBRMerger...")
    _request("DELETE", f"/api/v3/movie/{movie_id}?deleteFiles=true&addImportExclusion=false")
    info("Filme removido do PTBRMerger com sucesso.")


def rescan_movie(movie_id: int) -> None:
    debug(f"Solicitando rescan do filme ID {movie_id}...")
    _request("POST", "/api/v3/command", json={"name": "RescanMovie", "movieId": movie_id})
    info("Rescan solicitado. Metadados serão atualizados em breve.")
