import json
import subprocess
import re
from pathlib import Path
from typing import Optional

from src.config import get_config
from src.notifier import debug, info, warning, error

config = get_config()

def _probe_file(filepath: Path) -> dict:
    """
    Executa o ffprobe utilizando subprocess com as flags indicadas no PRD:
    - -show_streams e -show_format em uma única chamada.
    Retorna o JSON parseado contendo a estrutura de streams e format (duração).
    """
    ffprobe_path = config.ffmpeg.ffprobe_path
    cmd = [
        str(ffprobe_path),
        "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        "-show_format",
        str(filepath)
    ]
    
    try:
        debug(f"Executando ffprobe em: {filepath.name}")
        # text=True envia string pra stdout invés de bytes (facilita o json.loads)
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        
        if not result.stdout or result.stdout.strip() == "":
            error(f"O ffprobe retornou um stdout vazio para {filepath.name}")
            return {}
            
        return json.loads(result.stdout)
    except subprocess.CalledProcessError as e:
        error(f"Erro executando ffprobe em {filepath.name}. STDERR: {e.stderr}")
        return {}
    except json.JSONDecodeError as e:
        error(f"Erro ao decodificar JSON do ffprobe para {filepath.name}: {str(e)}")
        return {}

def _is_ptbr_stream(tags: dict) -> bool:
    """
    Verifica se o idioma é PT-BR avaliando tanto tags.language quanto tags.title.
    Aceita as tags estritas exigidas pelo PRD e também verifica substrings descritivas (ex "Português (Brasil)").
    """
    language = tags.get("language", "").lower()
    title = tags.get("title", "").lower()
    
    allowed_exact = {"por", "pt", "pt-br", "ptbr", "portuguese", "português"}
    
    if language in allowed_exact or title in allowed_exact:
        return True
        
    # Verifica descriptors estendidos comuns em pt-br dentro do title
    # ex: "Brazillian Portuguese", "Português (Brasil)", "Language: pt-BR"
    for tag in ["pt-br", "ptbr", "portuguese", "português"]:
        if tag in title:
            return True
            
    # Usa pattern isolation para 'pt' e 'por' para evitar falso positivo (ex: 'import')
    if re.search(r'\b(pt|por)\b', title):
        return True
        
    return False

def get_ptbr_stream_index(filepath: Path) -> Optional[int]:
    """
    Itera sobre TODOS os streams (não assume posição fixa) procurando um
    stream de audio onde linguagem ou titulo indicam ser Português.
    """
    probe = _probe_file(filepath)
    streams = probe.get("streams", [])
    
    for stream in streams:
        if stream.get("codec_type") != "audio":
            continue
            
        tags = stream.get("tags", {})
        
        if _is_ptbr_stream(tags):
            idx = stream.get("index")
            debug(f"Faixa PT-BR encontrada no índice {idx} em {filepath.name}")
            return idx
            
    # Chega ao fim das iterações sem sucessos    
    debug(f"Nenhuma faixa PT-BR encontrada em {filepath.name}")
    return None

def get_allowed_streams(filepath: Path) -> list[int]:
    """
    Lista os índices de streams (áudio/legenda) cujos idiomas sejam permitidos:
    'por', 'eng', 'jpn', 'und' ou não definidos (ausência de tags).
    """
    probe = _probe_file(filepath)
    streams = probe.get("streams", [])
    
    allowed_indices = []
    
    allowed_langs_exact = {
        "por", "pt", "pt-br", "ptbr", "portuguese", "português",
        "eng", "en", "english", "jpn", "ja", "japanese", "und"
    }
    
    for stream in streams:
        ctype = stream.get("codec_type")
        if ctype not in ("audio", "subtitle"):
            continue
            
        tags = stream.get("tags", {})
        if not tags:
            allowed_indices.append(stream.get("index"))
            continue
            
        language = tags.get("language", "").lower()
        title = tags.get("title", "").lower()
        
        is_allowed = False
        
        if language == "" or language in allowed_langs_exact or title in allowed_langs_exact:
            is_allowed = True
            
        if not is_allowed:
            # Substrings seguras
            for tag in ["pt-br", "ptbr", "portuguese", "português", "english", "japanese"]:
                if tag in title:
                    is_allowed = True
                    break
        
        if not is_allowed:
            # Regex boundaries for short tags
            if re.search(r'\b(pt|por|en|eng|ja|jpn|und)\b', title):
                is_allowed = True

        if is_allowed:
            allowed_indices.append(stream.get("index"))
            
    return allowed_indices

def has_ptbr_audio(filepath: Path) -> bool:
    """Retorna flag simples sobre presença da faixa pt-br no arquivo."""
    return get_ptbr_stream_index(filepath) is not None

def get_duration(filepath: Path) -> float:
    """Busca a duração em float a partir de format.duration retornado do PRD JSON."""
    probe = _probe_file(filepath)
    format_info = probe.get("format", {})
    duration_str = format_info.get("duration", "0")
    
    try:
        return float(duration_str)
    except ValueError:
        warning(f"Duração formatada ({duration_str}) inválida pelo ffprobe no arquivo {filepath.name}.")
        return 0.0

def validate_sync(file_4k: Path, file_1080p: Path) -> bool:
    """
    Mede a sincronia entre a versão 4k originar e o rip 1080p, 
    usando tolerância de segundos definida nas configurações (default 5s).
    """
    max_diff = config.sync.max_duration_diff_seconds
    
    duration_4k = get_duration(file_4k)
    duration_1080p = get_duration(file_1080p)
    
    if duration_4k == 0.0 or duration_1080p == 0.0:
        warning("Não foi possível validar sincronia (Duração inválida ou nula).")
        return False
        
    diff = abs(duration_4k - duration_1080p)
    
    # Especificação do PRD: "deve logar a diferença exata para facilitar debug"
    info(f"[Sincronia] 4K: {duration_4k:.3f}s | 1080p: {duration_1080p:.3f}s | Diferença exata: {diff:.3f}s")
    
    if diff > max_diff:
        warning(f"Erro de Sincronia: Diferença de {diff:.3f}s excede o limite estipulado de {max_diff}s.")
        return False
        
    return True
