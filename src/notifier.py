import sys
import requests
from loguru import logger
from src.config import get_config

# Carrega a configuração global
config = get_config()

# Remove handlers padrões do loguru
logger.remove()

# Adiciona handler para Stdout com base no nível configurado
logger.add(
    sys.stdout,
    level=config.logging.level,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>"
)

# Adiciona handler de arquivo se configurado
if config.logging.file:
    import os
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    log_path = os.path.join(base_dir, config.logging.file)
    logger.add(
        log_path,
        level=config.logging.level,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
        rotation="10 MB",
        retention="5 days",
        encoding="utf-8"
    )

# Alias rápidos para os métodos de log do Loguru para import direto nos outros módulos
info = logger.info
error = logger.error
warning = logger.warning
success = logger.success
debug = logger.debug

def notify_status(status: str, context: dict) -> None:
    """
    Registra no log e envia notificação para o Discord (se configurado)
    baseado no status da execução atual do Merger.
    
    Status esperados:
    - SUCCESS
    - SKIPPED_HAS_PTBR
    - NOT_FOUND
    - NOT_FOUND_STREAM
    - SYNC_MISMATCH
    - DUPLICATE_CALL
    - ERROR
    """
    message = _build_message(status, context)
    
    # Define o nível de log apropriado
    if status in ("SUCCESS", "SKIPPED_HAS_PTBR", "DUPLICATE_CALL"):
        info(message)
    elif status in ("NOT_FOUND", "NOT_FOUND_STREAM", "SYNC_MISMATCH", "ERROR"):
        error(message)
    else:
        warning(message)
        
    # Envia pro webhook, caindo silenciosamente se não configurado
    _send_discord_webhook(status, message)

def _build_message(status: str, context: dict) -> str:
    title = context.get("title", "Título Desconhecido")
    year = context.get("year", "")
    movie_name = f"{title} ({year})" if year else title
    
    if status == "SUCCESS":
        return f"✅ SUCCESS: Áudio PT-BR injetado com sucesso no filme {movie_name}"
    elif status == "SKIPPED_HAS_PTBR":
        return f"⏭️ SKIPPED: O filme {movie_name} já possui faixa de áudio PT-BR."
    elif status == "NOT_FOUND":
        return f"🔍 NOT_FOUND: Nenhuma versão PT-BR aceitável encontrada para o filme {movie_name}."
    elif status == "NOT_FOUND_STREAM":
        return f"⚠️ NOT_FOUND_STREAM: Versão baixada, mas stream de idioma 'por' ausente em {movie_name}."
    elif status == "SYNC_MISMATCH":
        diff = context.get("diff", "Desconhecida")
        return f"⏱️ SYNC_MISMATCH: Diferença de duração muito grande ({diff}s) detectada para {movie_name}."
    elif status == "DUPLICATE_CALL":
        return f"🔄 DUPLICATE_CALL: Trigger abortado; processo já estava em andamento para {movie_name}."
    elif status == "ERROR":
        err_msg = context.get("error", "Erro não especificado")
        return f"❌ ERROR: Falha processando {movie_name} - {err_msg}"
        
    return f"Status desconhecido '{status}' para o filme {movie_name}"

def _send_discord_webhook(status: str, message: str) -> None:
    webhook_url = config.notifications.discord_webhook_url
    
    # Se a URL vier vazia, null ou contendo apenas espaços brancos, aborta a notificação
    if not webhook_url or not str(webhook_url).strip():
        debug("Discord Webhook desativado no config.yml. Pulando notificação remota.")
        return
        
    # Tabela de cores RGB hex convertidas para int no formato do Discord
    colors = {
        "SUCCESS": 0x28A745,             # Verde sucesso
        "SKIPPED_HAS_PTBR": 0x6C757D,    # Cinza claro
        "DUPLICATE_CALL": 0x6C757D,     
        "NOT_FOUND": 0xFD7E14,           # Laranja warning
        "NOT_FOUND_STREAM": 0xFD7E14,   
        "SYNC_MISMATCH": 0xDC3545,       # Vermelho erro
        "ERROR": 0xDC3545
    }
    
    payload = {
        "username": "PTBRMerger Bot",
        "embeds": [
            {
                "title": f"Status: {status}",
                "description": message,
                "color": colors.get(status, 0x6C757D)
            }
        ]
    }
    
    try:
        response = requests.post(webhook_url, json=payload, timeout=5)
        response.raise_for_status()
    except Exception as e:
        error(f"Falha ao enviar webhook do Discord: {e}")
