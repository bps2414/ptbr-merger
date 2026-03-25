import time
from enum import Enum
from pathlib import Path
from typing import List, Optional, Tuple
from urllib.parse import urljoin

import requests

from src.config import get_config
from src.notifier import debug, error, info
from src.sync_intelligence import GroupHistoryManager, parse_release_metadata

config = get_config()
BASE_DIR = Path(__file__).resolve().parent.parent
group_history_manager = GroupHistoryManager(
    BASE_DIR / config.logging.group_history_file,
    max_entries=getattr(config.logging, "group_history_max_entries", 1000),
)


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
_LAST_SEARCH_SUMMARY: dict[str, dict] = {}


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


def get_movie_by_file_path(file_path: str | Path) -> Optional[dict]:
    target_path = Path(file_path)
    target_path_str = str(target_path).lower()
    imdb_marker = None
    for part in target_path.parts:
        if "[imdbid-" in part.lower():
            imdb_marker = part.lower().split("[imdbid-")[-1].split("]")[0]
            break

    movies = _request("GET", "/api/v3/movie", timeout=60)
    for movie in movies if isinstance(movies, list) else []:
        movie_file_path = str((movie.get("movieFile") or {}).get("path") or "").lower()
        root_path = str(movie.get("path") or "").lower()
        imdb_id = str(movie.get("imdbId") or "").lower()
        if movie_file_path and movie_file_path == target_path_str:
            return movie
        if root_path and target_path_str.startswith(root_path):
            return movie
        if imdb_marker and imdb_id and imdb_marker == imdb_id:
            return movie
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


def _keyword_present(title_lower: str, keyword: str) -> bool:
    import re

    keyword_lower = keyword.lower()
    normalized_title = re.sub(r"[^a-z0-9]+", " ", title_lower).strip()
    normalized_keyword = re.sub(r"[^a-z0-9]+", " ", keyword_lower).strip()

    if keyword_lower in title_lower:
        return True
    if normalized_keyword and normalized_keyword in normalized_title:
        return True
    if len(keyword_lower) <= 3:
        if bool(re.search(rf"\b{re.escape(keyword_lower)}\b", title_lower)):
            return True
        if normalized_keyword and bool(re.search(rf"\b{re.escape(normalized_keyword)}\b", normalized_title)):
            return True
    return False


def _keyword_group_matches(title_lower: str, keywords: List[str]) -> list[str]:
    return [keyword for keyword in keywords if _keyword_present(title_lower, keyword)]


def _ptbr_keyword_groups() -> tuple[list[str], list[str], list[str]]:
    all_keywords = list(getattr(config.ptbr_keywords, "high_priority", [])) + list(getattr(config.ptbr_keywords, "medium_priority", []))
    dubbed_keywords = [keyword for keyword in all_keywords if any(token in keyword.lower() for token in ("dublado", "dublagem", "nacional"))]
    dual_keywords = [keyword for keyword in all_keywords if any(token in keyword.lower() for token in ("dual", "multi"))]
    ptbr_keywords = [
        keyword
        for keyword in getattr(config.ptbr_keywords, "high_priority", [])
        if keyword not in dubbed_keywords and keyword not in dual_keywords
    ]
    return dubbed_keywords, dual_keywords, ptbr_keywords


def _matched_br_indexer(indexer_name: str) -> str | None:
    for br_indexer in getattr(config.ptbr_keywords, "indexer_names_br", []):
        if br_indexer.lower() in indexer_name.lower():
            return br_indexer
    return None


def _has_minimum_ptbr_evidence(release: dict) -> tuple[bool, str]:
    title_lower = str(release.get("title", "") or "").lower()
    indexer_name = str(release.get("indexer", "") or "")
    dubbed_keywords, dual_keywords, ptbr_keywords = _ptbr_keyword_groups()

    if _keyword_group_matches(title_lower, dubbed_keywords):
        return True, "dubbed"
    if _keyword_group_matches(title_lower, ptbr_keywords):
        return True, "explicit-ptbr"

    br_indexer = _matched_br_indexer(indexer_name)
    if br_indexer and _keyword_group_matches(title_lower, dual_keywords):
        return True, f"dual-on-br-indexer:{br_indexer}"

    return False, "missing-ptbr-evidence"


def _has_relaxed_ptbr_evidence(release: dict) -> tuple[bool, str]:
    title_lower = str(release.get("title", "") or "").lower()
    indexer_name = str(release.get("indexer", "") or "")
    dubbed_keywords, dual_keywords, ptbr_keywords = _ptbr_keyword_groups()

    if _keyword_group_matches(title_lower, dual_keywords) and _keyword_group_matches(title_lower, ptbr_keywords):
        return True, "dual-with-localized-title"

    br_indexer = _matched_br_indexer(indexer_name)
    if br_indexer and _keyword_group_matches(title_lower, dual_keywords):
        return True, f"dual-soft-on-br-indexer:{br_indexer}"

    return False, "missing-soft-ptbr-evidence"


def _has_exploratory_ptbr_evidence(release: dict) -> tuple[bool, str]:
    title_lower = str(release.get("title", "") or "").lower()
    _dubbed_keywords, dual_keywords, _ptbr_keywords = _ptbr_keyword_groups()

    if not _keyword_group_matches(title_lower, dual_keywords):
        return False, "missing-exploratory-dual"

    foreign_markers = [
        "latino",
        "dual-lat",
        " la película",
        "vfq",
        "ita-eng",
        " ita ",
        ".ita.",
        " iта",
        "italian",
        "spanish",
        "castellano",
        " lektor ",
        "polish",
        "ukr",
        "russian",
        " hindi ",
    ]
    if any(marker in title_lower for marker in foreign_markers):
        return False, "explicit-foreign-audio"

    return True, "dual-exploratory"


def _extract_availability_metric(release: dict, *field_names: str) -> int | None:
    for field_name in field_names:
        value = release.get(field_name)
        if value in (None, ""):
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


def _seeders_for_release(release: dict) -> int | None:
    return _extract_availability_metric(release, "seeders", "seedCount", "seedersCount")


def _peers_for_release(release: dict) -> int | None:
    return _extract_availability_metric(release, "peers", "peersCount", "leechers", "leechersCount")


def _protocol_for_release(release: dict) -> str | None:
    return release.get("protocol") or release.get("downloadProtocol")


def get_last_release_search_summary(tmdb_id: str) -> dict:
    return dict(_LAST_SEARCH_SUMMARY.get(str(tmdb_id), {}))


def _calculate_tiebreaker(release: dict, original_cut_keywords: List[str]) -> Tuple[int, str]:
    title = release.get("title", "")
    title_lower = title.lower()
    title_upper = title.upper()
    indexer_name = release.get("indexer", "")
    quality_name = release.get("quality", {}).get("quality", {}).get("name", "")

    score = 0
    matched_keywords = []

    dubbed_keywords, dual_keywords, ptbr_keywords = _ptbr_keyword_groups()

    if _keyword_group_matches(title_lower, dubbed_keywords):
        score += 9
        matched_keywords.append("[PTBR]dublado")

    if _keyword_group_matches(title_lower, ptbr_keywords):
        score += 7
        matched_keywords.append("[PTBR]audio")

    if _keyword_group_matches(title_lower, dual_keywords):
        score += 10
        matched_keywords.append("[DUAL]multi")

    br_indexer = _matched_br_indexer(indexer_name)
    if br_indexer:
        score += 4
        matched_keywords.append(f"[SRC]indexer:{br_indexer}")

    if "WEBDL" in quality_name.upper() or "WEB-DL" in quality_name.upper():
        score += 1
        matched_keywords.append("[SRC]WEBDL")

    cut_keywords_list = ["REPACK", "EXTENDED", "THEATRICAL", "IMAX", "DIRECTORS.CUT", "UNRATED"]
    candidate_cut_keywords = [keyword for keyword in cut_keywords_list if keyword in title_upper]

    for keyword in cut_keywords_list:
        has_in_4k = keyword in original_cut_keywords
        has_in_1080p = keyword in candidate_cut_keywords

        if has_in_4k and has_in_1080p:
            score += 5
            matched_keywords.append(f"[CUT]+{keyword}")
        elif has_in_4k and not has_in_1080p:
            score -= 10
            matched_keywords.append(f"[CUT]-Falta {keyword}")
        elif not has_in_4k and has_in_1080p:
            score -= 10
            matched_keywords.append(f"[CUT]-Sobra {keyword}")

    if matched_keywords:
        return score, f"Tiebreaker {score} (Keywords: {', '.join(matched_keywords)})"
    return score, f"Tiebreaker {score}"


def find_best_ptbr_release(tmdb_id: str, exclude_titles: Optional[List[str]] = None) -> List[dict]:
    exclude_titles = exclude_titles or []
    min_score = getattr(config.radarr, "ptbrmerger_min_score", 10000)
    summary = {
        "tmdbId": str(tmdb_id),
        "total_releases": 0,
        "eligible_count": 0,
        "soft_candidate_count": 0,
        "exploratory_candidate_count": 0,
        "skipped_no_seeds": [],
        "skipped_no_ptbr_evidence": [],
        "reason": "NO_MATCHES",
    }
    max_candidates = getattr(config.radarr, "ptbrmerger_max_candidates", 10)

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
    source_4k = parse_release_metadata(Path(file_4k_name).name if file_4k_name else "")["source"]

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

    summary["total_releases"] = len(releases)
    all_scores = sorted([release.get("customFormatScore", 0) for release in releases], reverse=True)
    info(f"Busca retornou {len(releases)} releases. Top 5 scores: {all_scores[:5]}")

    candidates = []

    for release in releases:
        cf_score = release.get("customFormatScore", 0)
        title = release.get("title", "")
        quality_name = release.get("quality", {}).get("quality", {}).get("name", "")
        url = release.get("downloadUrl") or release.get("magnetUrl")
        seeders = _seeders_for_release(release)
        peers = _peers_for_release(release)
        protocol = _protocol_for_release(release)
        release_metadata = parse_release_metadata(title)

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
        if seeders is not None and seeders <= 0:
            info(
                f"Release ignorada por indisponibilidade de seeds: {title} "
                f"[seeders={seeders}, peers={peers if peers is not None else 'N/A'}]"
            )
            summary["skipped_no_seeds"].append(
                {
                    "title": title,
                    "indexer": release.get("indexer", ""),
                    "seeders": seeders,
                    "peers": peers,
                }
            )
            continue
        has_ptbr_evidence, evidence_reason = _has_minimum_ptbr_evidence(release)
        if not has_ptbr_evidence:
            info(f"Release ignorada por falta de evidência PT-BR: {title} [indexer={release.get('indexer', '')}]")
            summary["skipped_no_ptbr_evidence"].append(
                {
                    "title": title,
                    "indexer": release.get("indexer", ""),
                    "reason": evidence_reason,
                }
            )
            continue

        tiebreaker_score, justificativa = _calculate_tiebreaker(release, original_cut_keywords)
        history_bonus, history_reason = group_history_manager.score_candidate(
            source_4k=source_4k,
            source_1080p=release_metadata["source"],
            group=release_metadata["group"],
        )
        effective_score = tiebreaker_score + history_bonus
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
                "seeders": seeders,
                "peers": peers,
                "protocol": protocol,
                "rejection_reason": None,
                "group": release_metadata["group"],
                "source_1080p": release_metadata["source"],
                "source_4k": source_4k,
                "history_bonus": history_bonus,
                "history_reason": history_reason,
                "effective_score": effective_score,
                "history_metadata": release_metadata,
            }
        )

    if not candidates:
        if summary["skipped_no_seeds"]:
            summary["reason"] = "NO_AVAILABLE_SEEDS"
        _LAST_SEARCH_SUMMARY[str(tmdb_id)] = summary
        debug(f"Nenhum release elegível encontrado (min_score={min_score}).")
        return []

    candidates.sort(
        key=lambda candidate: (
            candidate["effective_score"],
            candidate["seeders"] if candidate.get("seeders") is not None else -1,
            1 if "WEBDL" in candidate["quality"].upper() or "WEB-DL" in candidate["quality"].upper() else 0,
            -candidate["size"],
        ),
        reverse=True,
    )

    for index, candidate in enumerate(candidates[:max_candidates], 1):
        info(
            f"Candidato #{index} [Tiebreaker {candidate['tiebreaker_score']}][History {candidate['history_bonus']}][{candidate['quality']}]: "
            f"{candidate['title']} ({candidate['justificativa']} | {candidate['history_reason']})"
        )

    summary["eligible_count"] = len(candidates[:max_candidates])
    summary["reason"] = "OK"
    _LAST_SEARCH_SUMMARY[str(tmdb_id)] = summary
    return candidates[:max_candidates]


_find_best_ptbr_release_strict = find_best_ptbr_release


def _candidate_sort_key(candidate: dict) -> tuple:
    bank_rank = {"strict": 3, "soft": 2, "exploratory": 1}.get(candidate.get("evidence_level", "strict"), 0)
    return (
        bank_rank,
        candidate["effective_score"],
        candidate["seeders"] if candidate.get("seeders") is not None else -1,
        1 if "WEBDL" in candidate["quality"].upper() or "WEB-DL" in candidate["quality"].upper() else 0,
        -candidate["size"],
    )


def _build_release_candidate(
    release: dict,
    original_cut_keywords: list[str],
    source_4k: str,
    evidence_level: str,
    evidence_reason: str,
) -> dict:
    title = release.get("title", "")
    quality_name = release.get("quality", {}).get("quality", {}).get("name", "")
    seeders = _seeders_for_release(release)
    peers = _peers_for_release(release)
    protocol = _protocol_for_release(release)
    release_metadata = parse_release_metadata(title)
    tiebreaker_score, justificativa = _calculate_tiebreaker(release, original_cut_keywords)
    history_bonus, history_reason = group_history_manager.score_candidate(
        source_4k=source_4k,
        source_1080p=release_metadata["source"],
        group=release_metadata["group"],
    )
    effective_score = tiebreaker_score + history_bonus
    if evidence_level == "soft":
        effective_score -= 6
        justificativa = f"{justificativa} | soft-evidence:{evidence_reason}"
    elif evidence_level == "exploratory":
        effective_score -= 10
        justificativa = f"{justificativa} | exploratory-evidence:{evidence_reason}"

    return {
        "title": title,
        "url": release.get("downloadUrl") or release.get("magnetUrl"),
        "cf_score": release.get("customFormatScore", 0),
        "tiebreaker_score": tiebreaker_score,
        "justificativa": justificativa,
        "quality": quality_name,
        "size": release.get("size", 0),
        "indexer": release.get("indexer", ""),
        "downloadUrl": release.get("downloadUrl"),
        "magnetUrl": release.get("magnetUrl"),
        "seeders": seeders,
        "peers": peers,
        "protocol": protocol,
        "rejection_reason": None,
        "group": release_metadata["group"],
        "source_1080p": release_metadata["source"],
        "source_4k": source_4k,
        "history_bonus": history_bonus,
        "history_reason": history_reason,
        "effective_score": effective_score,
        "history_metadata": release_metadata,
        "evidence_level": evidence_level,
        "evidence_reason": evidence_reason,
    }


def find_best_ptbr_release(tmdb_id: str, exclude_titles: Optional[List[str]] = None) -> List[dict]:
    exclude_titles = exclude_titles or []
    max_candidates = getattr(config.radarr, "ptbrmerger_max_candidates", 10)
    strict_candidates = _find_best_ptbr_release_strict(tmdb_id, exclude_titles=exclude_titles)
    for candidate in strict_candidates:
        candidate.setdefault("evidence_level", "strict")
        candidate.setdefault("evidence_reason", "minimum-ptbr-evidence")
    if len(strict_candidates) >= max_candidates:
        return strict_candidates[:max_candidates]

    movie = get_movie_by_tmdbid(tmdb_id)
    if not movie:
        return strict_candidates

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
    source_4k = parse_release_metadata(Path(file_4k_name).name if file_4k_name else "")["source"]

    try:
        releases = _request("GET", f"/api/v3/release?movieId={movie['id']}", timeout=120)
    except Exception:
        return strict_candidates

    strict_titles = {candidate["title"] for candidate in strict_candidates}
    soft_candidates = []
    exploratory_candidates = []
    for release in releases or []:
        title = release.get("title", "")
        quality_name = release.get("quality", {}).get("quality", {}).get("name", "")
        url = release.get("downloadUrl") or release.get("magnetUrl")
        cf_score = release.get("customFormatScore", 0)
        seeders = _seeders_for_release(release)

        if cf_score < getattr(config.radarr, "ptbrmerger_min_score", 10000) or not url:
            continue
        if title in exclude_titles or title in strict_titles:
            continue
        if _is_blacklisted(title) or _is_blocked_quality(quality_name):
            continue
        if seeders is not None and seeders <= 0:
            continue
        strict_ok, _ = _has_minimum_ptbr_evidence(release)
        if strict_ok:
            continue
        soft_ok, soft_reason = _has_relaxed_ptbr_evidence(release)
        if soft_ok:
            candidate = _build_release_candidate(release, original_cut_keywords, source_4k, "soft", soft_reason)
            soft_candidates.append(candidate)
            info(
                f"Release mantida como fallback permissivo: {title} "
                f"[indexer={release.get('indexer', '')}] | motivo={soft_reason}"
            )
            continue

        exploratory_ok, exploratory_reason = _has_exploratory_ptbr_evidence(release)
        if not exploratory_ok:
            continue
        candidate = _build_release_candidate(release, original_cut_keywords, source_4k, "exploratory", exploratory_reason)
        exploratory_candidates.append(candidate)
        info(
            f"Release mantida como fallback exploratório: {title} "
            f"[indexer={release.get('indexer', '')}] | motivo={exploratory_reason}"
        )

    merged = strict_candidates + soft_candidates + exploratory_candidates
    merged.sort(key=_candidate_sort_key, reverse=True)

    summary = get_last_release_search_summary(tmdb_id)
    if summary:
        summary["eligible_count"] = len([c for c in merged[:max_candidates] if c.get("evidence_level", "strict") == "strict"])
        summary["soft_candidate_count"] = len([c for c in merged[:max_candidates] if c.get("evidence_level") == "soft"])
        summary["exploratory_candidate_count"] = len([c for c in merged[:max_candidates] if c.get("evidence_level") == "exploratory"])
        _LAST_SEARCH_SUMMARY[str(tmdb_id)] = summary

    if soft_candidates or exploratory_candidates:
        for index, candidate in enumerate(merged[:max_candidates], 1):
            info(
                f"Candidato #{index} [{candidate.get('evidence_level', 'strict')}][Tiebreaker {candidate['tiebreaker_score']}][History {candidate['history_bonus']}][{candidate['quality']}]: "
                f"{candidate['title']} ({candidate['justificativa']} | {candidate['history_reason']})"
            )
    return merged[:max_candidates]


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
