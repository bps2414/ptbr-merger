import requests
import time
from dataclasses import dataclass
from urllib.parse import urljoin
from typing import Optional
from urllib.parse import parse_qs, urlparse

from src.config import get_config
from src.notifier import debug, info, warning, error

config = get_config()

_BASE_URL = config.qbittorrent.url
_USERNAME = config.qbittorrent.username
_PASSWORD = config.qbittorrent.password

_TORRENT_POLL_ATTEMPTS = 5
_TORRENT_POLL_INTERVAL_SECONDS = 1
_AUTO_RESUME_STATES = {"pausedDL", "stoppedDL"}
_ACTIVE_STATES = {
    "metaDL",
    "forcedMetaDL",
    "downloading",
    "forcedDL",
    "queuedDL",
    "stalledDL",
    "checkingDL",
    "checkingResumeData",
    "allocating",
    "moving",
}


@dataclass
class QbitAddResult:
    success: bool
    torrent_hash: str | None = None
    state: str | None = None
    content_path: str | None = None
    save_path: str | None = None
    existing: bool = False
    completed: bool = False


def _build_tag(tmdb_id: str) -> str:
    return f"ptbrmerger-tmdbid-{tmdb_id}"


def _list_torrents_by_tag(session: requests.Session, tag: str) -> list[dict]:
    api_url = urljoin(_BASE_URL, "/api/v2/torrents/info")
    try:
        response = session.get(
            api_url,
            params={"filter": "all", "tag": tag},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, list) else []
    except (requests.exceptions.RequestException, ValueError) as e:
        warning(f"Falha consultando lista de torrents no qBittorrent para a tag {tag}: {e}")
        return []


def _resume_torrents(session: requests.Session, torrents: list[dict]) -> None:
    hashes = sorted({t.get("hash", "") for t in torrents if t.get("state") in _AUTO_RESUME_STATES and t.get("hash")})
    if not hashes:
        return

    api_url = urljoin(_BASE_URL, "/api/v2/torrents/resume")
    try:
        session.post(api_url, data={"hashes": "|".join(hashes)}, timeout=10).raise_for_status()
        debug(f"Torrent(s) pausado(s) retomados no qBittorrent: {', '.join(h[:8] for h in hashes)}")
    except requests.exceptions.RequestException as e:
        warning(f"Não foi possível enviar comando de resume ao qBittorrent: {e}")


def _progress_pct(torrent: dict) -> float:
    try:
        return float(torrent.get("progress", 0) or 0) * 100
    except (TypeError, ValueError):
        return 0.0


def _is_confirmed_state(torrent: dict) -> bool:
    state = str(torrent.get("state", "") or "")
    progress = _progress_pct(torrent)
    return state in _ACTIVE_STATES or progress >= 100.0


def _describe_torrent(torrent: dict) -> str:
    name = torrent.get("name", "(sem nome)")
    state = torrent.get("state", "unknown")
    return f"{name} | state={state} | progress={_progress_pct(torrent):.1f}%"


def _torrent_to_result(torrent: dict, success: bool = True, existing: bool = False) -> QbitAddResult:
    return QbitAddResult(
        success=success,
        torrent_hash=torrent.get("hash"),
        state=torrent.get("state"),
        content_path=torrent.get("content_path"),
        save_path=torrent.get("save_path"),
        existing=existing,
        completed=_progress_pct(torrent) >= 100.0,
    )


def _apply_category_and_tags(session: requests.Session, torrent_hash: str, category: str, tag: str) -> None:
    try:
        session.post(
            urljoin(_BASE_URL, "/api/v2/torrents/setCategory"),
            data={"hashes": torrent_hash, "category": category},
            timeout=10,
        ).raise_for_status()
        session.post(
            urljoin(_BASE_URL, "/api/v2/torrents/addTags"),
            data={"hashes": torrent_hash, "tags": tag},
            timeout=10,
        ).raise_for_status()
    except requests.exceptions.RequestException as e:
        warning(f"Não foi possível aplicar category/tag no torrent {torrent_hash[:8]}...: {e}")


def _get_torrent_by_hash(session: requests.Session, torrent_hash: str) -> dict | None:
    try:
        response = session.get(
            urljoin(_BASE_URL, "/api/v2/torrents/info"),
            params={"hashes": torrent_hash},
            timeout=10,
        )
        response.raise_for_status()
        items = response.json()
        if isinstance(items, list) and items:
            return items[0]
    except (requests.exceptions.RequestException, ValueError) as e:
        warning(f"Falha consultando torrent por hash no qBittorrent ({torrent_hash[:8]}...): {e}")
    return None


def _extract_infohash_from_magnet(magnet_uri: str) -> str | None:
    query = parse_qs(urlparse(magnet_uri).query)
    xt_values = query.get("xt", [])
    for xt in xt_values:
        prefix = "urn:btih:"
        if xt.startswith(prefix):
            return xt[len(prefix):].lower()
    return None


def _extract_infohash_from_url(source_url: str) -> str | None:
    if not source_url:
        return None
    if source_url.startswith("magnet:?"):
        return _extract_infohash_from_magnet(source_url)

    current_url = source_url
    for _ in range(5):
        try:
            response = requests.get(current_url, timeout=15, allow_redirects=False)
        except requests.exceptions.RequestException as e:
            warning(f"Falha resolvendo URL do release para obter infohash: {e}")
            return None

        location = response.headers.get("location", "")
        if response.is_redirect and location:
            if location.startswith("magnet:?"):
                return _extract_infohash_from_magnet(location)
            current_url = location
            continue
        break

    return None

def login() -> Optional[requests.Session]:
    """
    Executa a autenticação (login) obrigatória na API v2 do qBittorrent.
    Retorna uma instância requests.Session com cache dos cookies ativado.
    Retorna None em falhas, que são logadas como ERROR mas não derrubam o trigger.
    """
    session = requests.Session()
    url = urljoin(_BASE_URL, "/api/v2/auth/login")
    
    payload = {
        "username": _USERNAME,
        "password": _PASSWORD
    }
    
    try:
        debug(f"Tentativa de login no qBittorrent: {_BASE_URL}")
        # A interface v2 de auth aceita Content-Type: application/x-www-form-urlencoded (usando arg 'data' em vez de json)
        response = session.post(url, data=payload, timeout=5)
        response.raise_for_status()
        
        # 'Ok.' é a resposta textual bem-sucedida padrão da API do qBit
        if response.text.strip() == "Ok.":
            debug("Autenticação no qBittorrent estabelecida com sucesso.")
            return session
        else:
            # Bypass de IP: Verifica se a sessão é válida apesar da falha (comum em Bypass de localhost do qBit)
            version_url = urljoin(_BASE_URL, "/api/v2/app/version")
            try:
                version_resp = session.get(version_url, timeout=5)
                if version_resp.status_code == 200:
                    debug("Autenticação no qBittorrent estabelecida com sucesso via bypass (localhost IP bypass).")
                    return session
            except Exception:
                pass
            
            error(f"QBittorrent rejeitou Auth: credenciais inválidas ou configuração errada. HTTP Res: {response.text}")
            return None
            
    except requests.exceptions.RequestException as e:
        error(f"Erro de conexão ao tentar logar na instância do qBittorrent ({_BASE_URL}): {e}")
        return None

def remove_torrent(torrent_hash: str, delete_files: bool = True) -> None:
    """
    Solicita remoção silenciosa do Torrent de id proveniente do Radarr On Import.
    Validação explícita preenchendo o requisito de logging preventivo por ser uma var
    passível de instabilidade de Hash vs InternalID.
    """
    # 1. Defesa Preventiva e Logging
    if not torrent_hash or not str(torrent_hash).strip():
        warning("Variável 'radarr_download_id' não fornecida, vazia ou nula pelo env. "
                "Ignorando deleção automática. (Limpe o respectivo Torrent DUAL manulmente).")
        return
        
    torrent_hash = str(torrent_hash).strip()
    debug(f"Hash candidato capturado da Env (radarr_download_id) para cleanup de torrent: '{torrent_hash}'.")
    
    if len(torrent_hash) < 30: # Hashes padrão tipo SHA1 tem lenght natural de 40 caracs
        warning(f"O Hash identificado ('{torrent_hash}') pode ser inválido para o qBit API v2. A API pode recusar esta operação.")

    # 2. Login Independente Reutilizando CookieSession
    session = login()
    if not session:
        error("Sessão HTTP inacessível para qBittorrent. Interrompendo envio do comando de DELETE de forma branda para seguir fluxo.")
        return

    # 3. Disparo via Client POST usando formato 'application/x-www-form-urlencoded' nativo
    url = urljoin(_BASE_URL, "/api/v2/torrents/delete")
    
    payload = {
        "hashes": torrent_hash,
        "deleteFiles": "true" if delete_files else "false"
    }
    
    try:
        debug(f"Acionando Payload HTTP pra Remoção de Tracker Cache em Qbit ({torrent_hash[:8]}...)")
        response = session.post(url, data=payload, timeout=10)
        response.raise_for_status()
        
        info(f"Torrent {torrent_hash[:8]}... e arquivos da mídia subjacente foram ordenados a exclusão no client local com sucesso.")
    except requests.exceptions.RequestException as e:
        error(f"Deleção Qbit via API abortada em Falha de Requisição: {e}. O áudio remanescerá no HDD do seeder.")

def add_torrent(url: str, tmdb_id: str) -> QbitAddResult:
    """
    Injeta um torrent (magnet ou arquivo URL) diretamente no qBittorrent, definindo
    a categoria e a tag contendo o TMDB ID para recuperação no script de post-download.
    """
    session = login()
    if not session:
        error("Sessão HTTP inacessível para qBittorrent. Não foi possível adicionar o torrent 1080p.")
        return QbitAddResult(success=False)
        
    api_url = urljoin(_BASE_URL, "/api/v2/torrents/add")
    tag = _build_tag(tmdb_id)
    category = "ptbrmerger"
    existing_torrents = _list_torrents_by_tag(session, tag)
    known_hashes = {t.get("hash") for t in existing_torrents if t.get("hash")}
    infohash = _extract_infohash_from_url(url)

    if infohash:
        duplicate_torrent = _get_torrent_by_hash(session, infohash)
        if duplicate_torrent:
            _apply_category_and_tags(session, infohash, category, tag)
            duplicate_torrent = _get_torrent_by_hash(session, infohash) or duplicate_torrent
            warning(
                f"O torrent PT-BR (TMDB {tmdb_id}) já existia no qBittorrent. Reaproveitando item duplicado: "
                f"{_describe_torrent(duplicate_torrent)}"
            )
            return _torrent_to_result(duplicate_torrent, success=True, existing=True)
    
    # Payload 'multipart/form-data' nativo do qBittorrent (requests converte 'data' auto nestes cases)
    data = {
        "urls": url,
        "category": category,
        "tags": tag,
        "stopped": "false",
    }
    
    try:
        debug(f"Enviando torrent pro qBittorrent com a tag {tag}...")
        response = session.post(api_url, data=data, timeout=10)
        response.raise_for_status()

        created_torrents = []
        matched_by_hash = None
        visible_torrents = existing_torrents
        for attempt in range(_TORRENT_POLL_ATTEMPTS):
            visible_torrents = _list_torrents_by_tag(session, tag)
            created_torrents = [t for t in visible_torrents if t.get("hash") not in known_hashes]
            if infohash:
                matched_by_hash = next((t for t in visible_torrents if (t.get("hash") or "").lower() == infohash), None)
            if created_torrents or matched_by_hash:
                break
            if attempt < _TORRENT_POLL_ATTEMPTS - 1:
                time.sleep(_TORRENT_POLL_INTERVAL_SECONDS)

        if not visible_torrents:
            if infohash:
                duplicate_torrent = _get_torrent_by_hash(session, infohash)
                if duplicate_torrent:
                    _apply_category_and_tags(session, infohash, category, tag)
                    duplicate_torrent = _get_torrent_by_hash(session, infohash) or duplicate_torrent
                    warning(
                        f"qBittorrent não exibiu o torrent pela tag {tag}, mas o infohash já existia localmente. "
                        f"Reaproveitando item: {_describe_torrent(duplicate_torrent)}"
                    )
                    return _torrent_to_result(duplicate_torrent, success=True, existing=True)

            error(
                f"qBittorrent respondeu HTTP {response.status_code}, mas nenhum torrent com a tag {tag} "
                "foi localizado após a injeção. O download provavelmente não entrou na fila."
            )
            return QbitAddResult(success=False)

        candidate_torrents = created_torrents or ([matched_by_hash] if matched_by_hash else visible_torrents)
        _resume_torrents(session, candidate_torrents)

        refreshed_torrents = _list_torrents_by_tag(session, tag) or visible_torrents
        candidate_torrents = [t for t in refreshed_torrents if t.get("hash") not in known_hashes]
        if not candidate_torrents and infohash:
            candidate_by_hash = next((t for t in refreshed_torrents if (t.get("hash") or "").lower() == infohash), None)
            if candidate_by_hash:
                candidate_torrents = [candidate_by_hash]
        if not candidate_torrents:
            candidate_torrents = refreshed_torrents
        representative = candidate_torrents[0]

        if not created_torrents and existing_torrents and representative.get("hash") in known_hashes:
            warning(
                f"Nenhum novo torrent foi criado para TMDB {tmdb_id}; reutilizando item já existente no qBittorrent: "
                f"{_describe_torrent(representative)}"
            )

        if _is_confirmed_state(representative):
            info(
                f"Torrent PT-BR (TMDB {tmdb_id}) confirmado no qBittorrent na categoria ptbrmerger: "
                f"{_describe_torrent(representative)}"
            )
            return _torrent_to_result(representative, success=True, existing=not bool(created_torrents))

        error(
            f"O torrent com a tag {tag} foi localizado no qBittorrent, mas permaneceu em estado não utilizável: "
            f"{_describe_torrent(representative)}"
        )
        return _torrent_to_result(representative, success=False, existing=not bool(created_torrents))
            
    except requests.exceptions.RequestException as e:
        error(f"Erro ao disparar torrent pro qBittorrent via API: {e}")
        return QbitAddResult(success=False)
