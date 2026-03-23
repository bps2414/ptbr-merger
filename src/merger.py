import os
import time
import subprocess
from pathlib import Path

from src.config import get_config
from src.notifier import debug, info, warning, error

config = get_config()

def extract_audio(file_1080p: Path, stream_idx: int, output_audio: Path) -> Path:
    """
    Extrai a faixa de áudio específica do arquivo 1080p sem re-encoding.
    Retorna o path do arquivo de áudio extraído temporário.
    """
    ffmpeg_path = config.ffmpeg.ffmpeg_path
    
    cmd = [
        str(ffmpeg_path),
        "-y",
        "-i", str(file_1080p),
        # Usamos o índice absoluto 0:{idx} pois o stream_idx vindo do ffprobe é absoluto entre todas as faixas (vídeo/áudio/legenda)
        "-map", f"0:{stream_idx}",  
        "-c:a", "copy",
        str(output_audio)
    ]
    
    try:
        debug(f"Processando FFmpeg Extração: {' '.join(cmd)}")
        # text=True ajuda a tratar o output stderr do ffmpeg em log sem encodings estranhos
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        info(f"Áudio PT-BR extraído com sucesso para: {output_audio.name}")
        return output_audio
    except subprocess.CalledProcessError as e:
        error(f"Erro ao extrair áudio com ffmpeg. Código: {e.returncode} | Output: \n{e.stderr}")
        raise

from src.analyzer import get_allowed_streams

def mux_audio(file_4k: Path, audio_ptbr: Path, output_tmp: Path) -> Path:
    """
    Injeta o áudio PT-BR como a primeira faixa no arquivo 4K, preservando o restante.
    Retorna o path do arquivo de mux temporário gerado.
    """
    ffmpeg_path = config.ffmpeg.ffmpeg_path
    
    allowed_indices = get_allowed_streams(file_4k)
    
    cmd = [
        str(ffmpeg_path),
        "-y",
        "-i", str(file_4k),
        "-i", str(audio_ptbr),
        "-map", "0:v",     # preserva o vídeo original
        "-map", "1:a",     # nova faixa de áudio PT-BR injetada primariamente
    ]
    
    for idx in allowed_indices:
        cmd.extend(["-map", f"0:{idx}"])
        
    cmd.extend([
        "-map_chapters", "0", # Preservar chapter markers originais do 4k
        "-c", "copy",      # preserva qualidade com zero raw-reencoding
        "-max_interleave_delta", "0", # Otimização Crítica para Smart TVs (Intercalação perfeita)
        "-metadata:s:a:0", "language=por",
        "-metadata:s:a:0", "title=Português (Brasil)",
        str(output_tmp)
    ])
    
    try:
        debug(f"Processando FFmpeg Mux: {' '.join(cmd)}")
        # Executa em Popen para capturar o stream stderr do ffmpeg ao vivo
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, universal_newlines=True)
        
        last_log_time = time.time()
        for line in process.stdout:
            # O codec do FFmpeg intercala as linhas de status como 'frame= 400 ... time=00:01:23.45 bitrate=...'
            if "time=" in line and "bitrate=" in line:
                current_time = time.time()
                # Atualizando o log a cada 10 segundos apenas, para evitar 1 milhão de linhas no terminal e no arquivo texto
                if current_time - last_log_time >= 10.0:
                    partes = line.strip().split("time=")
                    if len(partes) > 1:
                        progresso = partes[1].split(" ")[0]
                        info(f"Progresso de Fusão (Mux): Vídeo gerado até {progresso}")
                    last_log_time = current_time

        process.wait()
        if process.returncode != 0:
            error(f"Erro no FFmpeg durante processo de muxing. Código falha {process.returncode}")
            raise subprocess.CalledProcessError(process.returncode, cmd)
            
        info(f"Mux concluído com sucesso: {output_tmp.name}")
        return output_tmp
    except Exception as e:
        error(f"Falha catastrófica no FFmpeg muxing logger: {e}")
        raise

def replace_original(output_tmp: Path, file_4k: Path) -> None:
    """
    Garante a substituição do arquivo 4k original pelo output final processado.
    Tolerância a falhas baseada em Locking de Windows via Retry Loop com sleep.
    """
    if not output_tmp.exists():
        error(f"Substituição abortada: o arquivo temporário {output_tmp.name} gerado não existe no sub-path da biblioteca.")
        raise FileNotFoundError(f"Arquivo de saída temporário não encontrado: {output_tmp}")
        
    size_bytes = output_tmp.stat().st_size
    if size_bytes == 0:
        error(f"Substituição abortada preventivamente pela verificação de integridade: {output_tmp.name} está vazio (0 bytes).")
        raise ValueError("Arquivo temporário gerado pelo Muxing em formato Raw resultou em tamanho zerado devido à quebra de streams.")

    retries = 5
    delay = 3  # segundos
    
    for attempt in range(1, retries + 1):
        try:
            debug(f"Tentativa de substituição {attempt}/{retries}. Modificando o arquivo original...")
            os.replace(str(output_tmp), str(file_4k))
            info(f"Arquivo 4K original ({file_4k.name}) substituído com sucesso pela versão PTBR-Merger consolidada.")
            return
        except PermissionError as e:
            msg = f"Locking de Arquivos barrando a modificação de filesystem (Plex/Defender/Semente). Aguardando retry tick em {delay}s..."
            warning(f"PermissionError detectado (Tentativa {attempt}/{retries}): {msg}")
            
            if attempt < retries:
                time.sleep(delay)
            else:
                error("Falha contínua ao substituir arquivo original devido a Permissions. Excedeu as tentativas configuradas.")
                raise e
        except OSError as e:
            error(f"Erro de Input/Output Server-Side de disco crítico ao tentar substituir o arquivo final: {e}")
            raise
