import requests
from urllib.parse import urljoin
from pathlib import Path
from typing import Optional, Tuple, List
from enum import Enum

from src.config import get_config
from src.notifier import debug, info, warning, error

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

def _get_timeout() -> int:
    return getattr(config.radarr, "timeout", 10)

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
    except requests.exceptions.HTTPError as e:
        err_msg = e.response.text if e.response is not None else ""
        error(f"Erro de comunicação API Radarr ({method} {endpoint}): {e} - Body: {err_msg}")
        raise
    except requests.exceptions.RequestException as e:
        error(f"Erro de comunicação de rede API Radarr ({method} {endpoint}): {e}")
        raise

def get_profile_id(profile_name: str) -> int:
    if profile_name in _PROFILE_ID_CACHE:
        return _PROFILE_ID_CACHE[profile_name]
    profiles = _request("GET", "/api/v3/qualityprofile")
    for profile in profiles:
        if profile.get("name") == profile_name:
            pid = profile.get("id")
            _PROFILE_ID_CACHE[profile_name] = pid
            return pid
    raise ValueError(f"Profile '{profile_name}' não encontrado no Radarr.")

def get_tag_id(tag_name: str) -> int:
    if tag_name in _TAG_ID_CACHE:
        return _TAG_ID_CACHE[tag_name]
    tags = _request("GET", "/api/v3/tag")
    for tag in tags:
        if tag.get("label") == tag_name:
            tid = tag.get("id")
            _TAG_ID_CACHE[tag_name] = tid
            return tid
    raise ValueError(f"Tag '{tag_name}' não encontrada no Radarr.")

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
    """Verifica se o release deve ser rejeitado pela blacklist."""
    import re
    blacklist = getattr(config.ptbr_keywords, "blacklist", [])
    title_lower = title.lower()
    for word in blacklist:
        # Palavras curtas usam word boundary pra evitar falso positivo
        if len(word) <= 3:
            if re.search(rf'\b{re.escape(word.lower())}\b', title_lower):
                return True
        else:
            if word.lower() in title_lower:
                return True
    return False

def _is_blocked_quality(quality_name: str) -> bool:
    """Rejeita qualidades indesejadas para extração de áudio."""
    blocked = ["2160p", "4K", "TELECINE", "CAM", "TELESYNC", "HDCAM", "HDTV"]
    quality_upper = quality_name.upper()
    return any(b.upper() in quality_upper for b in blocked)

def _calculate_tiebreaker(release: dict, original_cut_keywords: List[str]) -> Tuple[int, str]:
    """
    Calcula score de desempate baseado exclusivamente em indicadores PT-BR.
    O score do Radarr (customFormatScore) serve APENAS como filtro de elegibilidade.
    
    Níveis:
    - Nível 4 (+8): keywords high_priority no título
    - Nível 3 (+4): release vem de indexer BR (por nome)
    - Nível 2 (+2): keywords medium_priority no título
    - Nível 1 (+1): qualidade WEBDL preferida sobre WEBRip
    """
    import re
    title = release.get("title", "")
    title_lower = title.lower()
    title_upper = title.upper()
    indexer_name = release.get("indexer", "")
    quality_name = release.get("quality", {}).get("quality", {}).get("name", "")

    score = 0
    matched_keywords = []

    # Nível 4 — keywords high_priority
    high_priority = getattr(config.ptbr_keywords, "high_priority", [])
    for kw in high_priority:
        if kw.lower() in title_lower:
            score += 8
            matched_keywords.append(f"[L4]{kw}")

    # Nível 3 — indexer BR por nome
    indexer_names_br = getattr(config.ptbr_keywords, "indexer_names_br", [])
    for br_indexer in indexer_names_br:
        if br_indexer.lower() in indexer_name.lower():
            score += 4
            matched_keywords.append(f"[L3]indexer:{br_indexer}")
            break

    # Nível 2 — keywords medium_priority
    medium_priority = getattr(config.ptbr_keywords, "medium_priority", [])
    for kw in medium_priority:
        if len(kw) <= 3:
            if re.search(rf'\b{re.escape(kw.lower())}\b', title_lower):
                score += 2
                matched_keywords.append(f"[L2]{kw}")
        else:
            if kw.lower() in title_lower:
                score += 2
                matched_keywords.append(f"[L2]{kw}")

    # Nível 1 — preferência por WEBDL
    if "WEBDL" in quality_name.upper() or "WEB-DL" in quality_name.upper():
        score += 1
        matched_keywords.append("[L1]WEBDL")

    # Avaliação de Corte de Compatibilidade
    cut_keywords_list = ["REPACK", "EXTENDED", "THEATRICAL", "IMAX", "DIRECTORS.CUT", "UNRATED"]
    candidate_cut_keywords = [kw for kw in cut_keywords_list if kw in title_upper]
    
    for kw in cut_keywords_list:
        has_in_4k = kw in original_cut_keywords
        has_in_1080p = kw in candidate_cut_keywords
        
        if has_in_4k and has_in_1080p:
            score += 5
            matched_keywords.append(f"[+5]{kw}")
        elif has_in_4k and not has_in_1080p:
            score -= 10
            matched_keywords.append(f"[-10]Falta {kw}")
        elif not has_in_4k and has_in_1080p:
            score -= 10
            matched_keywords.append(f"[-10]Sobra {kw}")

    justificativa = f"Tiebreaker {score} (Keywords: {', '.join(matched_keywords)})" if matched_keywords else f"Tiebreaker {score}"
    return score, justificativa

def find_best_ptbr_release(tmdb_id: str, exclude_titles: Optional[List[str]] = None) -> List[dict]:
    """
    Busca releases PT-BR e retorna lista ordenada de até 5 candidatos.
    O customFormatScore do Radarr serve APENAS para filtro de elegibilidade.
    A seleção final usa exclusivamente o tiebreaker multicamada PT-BR.
    
    Retorna lista de dicts com keys: title, url, tiebreaker_score, justificativa
    """
    exclude_titles = exclude_titles or []
    min_score = getattr(config.radarr, "ptbrmerger_min_score", 10000)

    movie = get_movie_by_tmdbid(tmdb_id)
    if not movie:
        error(f"Filme TMDB {tmdb_id} não encontrado na base do Radarr.")
        return []

    # Detectar o corte do 4K original pelo nome do arquivo
    file_4k_name = ""
    if "movieFile" in movie and movie["movieFile"]:
        file_4k_name = movie["movieFile"].get("path", "")
    elif "path" in movie: # Fallback se não tiver movie file associado, explora a pasta
        folder = Path(movie["path"])
        if folder.exists() and folder.is_dir():
            mkv_files = list(folder.rglob("*.mkv"))
            if mkv_files:
                file_4k_name = max(mkv_files, key=lambda p: p.stat().st_size).name
                
    cut_keywords_list = ["REPACK", "EXTENDED", "THEATRICAL", "IMAX", "DIRECTORS.CUT", "UNRATED"]
    original_cut_keywords = []
    if file_4k_name:
        file_4k_name_upper = Path(file_4k_name).name.upper()
        for kw in cut_keywords_list:
            if kw in file_4k_name_upper:
                original_cut_keywords.append(kw)
    
    if original_cut_keywords:
        info(f"Cortes detectados no arquivo 4K original: {original_cut_keywords}")
    else:
        debug("Nenhum corte especial (REPACK, EXTENDED, etc) detectado no arquivo original.")

    movie_id = movie["id"]
    info(f"Buscando releases para o filme ID {movie_id} no Radarr (pode demorar até 60s)...")

    try:
        releases = _request("GET", f"/api/v3/release?movieId={movie_id}", timeout=120)
    except Exception as e:
        error(f"Falha na busca interativa de releases: {e}")
        return []

    if not releases:
        debug("Busca retornou zero releases.")
        return []

    # Log dos top scores pra diagnóstico
    all_scores = sorted([r.get("customFormatScore", 0) for r in releases], reverse=True)
    info(f"Busca retornou {len(releases)} releases. Top 5 scores: {all_scores[:5]}")

    candidates = []

    for r in releases:
        cf_score = r.get("customFormatScore", 0)
        title = r.get("title", "")
        quality_name = r.get("quality", {}).get("quality", {}).get("name", "")
        url = r.get("downloadUrl") or r.get("magnetUrl")

        # Filtros de elegibilidade
        if cf_score < min_score:
            continue
        if not url:
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

        tiebreaker_score, justificativa = _calculate_tiebreaker(r, original_cut_keywords)

        info(f"Release detectada [Score {cf_score}][{quality_name}]: {title} | Tiebreaker: {tiebreaker_score}")

        candidates.append({
            "title": title,
            "url": url,
            "cf_score": cf_score,
            "tiebreaker_score": tiebreaker_score,
            "justificativa": justificativa,
            "quality": quality_name,
            "size": r.get("size", 0)
        })

    if not candidates:
        debug(f"Nenhum release elegível encontrado (min_score={min_score}).")
        return []

    # Ordena EXCLUSIVAMENTE pelo tiebreaker PT-BR
    # Em caso de empate: WEBDL > WEBRip, menor tamanho
    candidates.sort(key=lambda x: (
        x["tiebreaker_score"],
        1 if "WEBDL" in x["quality"].upper() or "WEB-DL" in x["quality"].upper() else 0,
        -x["size"]
    ), reverse=True)

    # Log dos top 5 candidatos
    top5 = candidates[:5]
    for i, c in enumerate(top5, 1):
        info(f"Candidato #{i} [Tiebreaker {c['tiebreaker_score']}][{c['quality']}]: {c['title']} ({c['justificativa']})")

    return top5

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
        else:
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
        "addOptions": {"searchForMovie": True}
    }

    debug(f"Adicionando {title} ({year}) no perfil PTBRMerger...")
    resp = _request("POST", "/api/v3/movie", json=payload)
    return resp.get("id"), MergerState.NEW_MOVIE

def remove_movie_ptbrmerger(movie_id: int) -> None:
    debug(f"Removendo filme ID {movie_id} do perfil PTBRMerger...")
    _request("DELETE", f"/api/v3/movie/{movie_id}?deleteFiles=true&addImportExclusion=false")
    info("Filme removido do PTBRMerger com sucesso.")

def rescan_movie(movie_id: int) -> None:
    debug(f"Solicitando rescan do filme ID {movie_id}...")
    _request("POST", "/api/v3/command", json={"name": "RescanMovie", "movieId": movie_id})
    info("Rescan solicitado. Metadados serão atualizados em breve.")
