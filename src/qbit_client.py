import requests
from urllib.parse import urljoin
from typing import Optional

from src.config import get_config
from src.notifier import debug, info, warning, error

config = get_config()

_BASE_URL = config.qbittorrent.url
_USERNAME = config.qbittorrent.username
_PASSWORD = config.qbittorrent.password

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

def add_torrent(url: str, tmdb_id: str) -> bool:
    """
    Injeta um torrent (magnet ou arquivo URL) diretamente no qBittorrent, definindo
    a categoria e a tag contendo o TMDB ID para recuperação no script de post-download.
    """
    session = login()
    if not session:
        error("Sessão HTTP inacessível para qBittorrent. Não foi possível adicionar o torrent 1080p.")
        return False
        
    api_url = urljoin(_BASE_URL, "/api/v2/torrents/add")
    
    # Payload 'multipart/form-data' nativo do qBittorrent (requests converte 'data' auto nestes cases)
    data = {
        "urls": url,
        "category": "ptbrmerger",
        "tags": f"ptbrmerger-tmdbid-{tmdb_id}",
    }
    
    try:
        debug(f"Enviando torrent pro qBittorrent com a tag ptbrmerger-tmdbid-{tmdb_id}...")
        response = session.post(api_url, data=data, timeout=10)
        response.raise_for_status()
        
        if response.text and "Ok." in response.text:
            info(f"Torrent PT-BR (TMDB {tmdb_id}) adicionado ao qBittorrent com sucesso na categoria ptbrmerger.")
            return True
        else:
            warning(f"qBittorrent retornou sucesso HTTP, mas body inesperado: {response.text}")
            return True # O retorno 'Fails.' as vezes significa duplicação, assumimos OK se HTTP 200
            
    except requests.exceptions.RequestException as e:
        error(f"Erro ao disparar torrent pro qBittorrent via API: {e}")
        return False
