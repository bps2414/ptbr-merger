import os
import subprocess
import time
from pathlib import Path
from typing import Optional

from src.analyzer import get_allowed_streams, validate_final_file
from src.config import get_config
from src.notifier import debug, error, info, warning

config = get_config()


def extract_audio(file_1080p: Path, stream_idx: int, output_audio: Path) -> Path:
    """
    Extrai a faixa de áudio específica do arquivo 1080p sem re-encoding.
    """
    ffmpeg_path = config.ffmpeg.ffmpeg_path
    cmd = [
        str(ffmpeg_path),
        "-y",
        "-i",
        str(file_1080p),
        "-map",
        f"0:{stream_idx}",
        "-c:a",
        "copy",
        str(output_audio),
    ]

    try:
        debug(f"Processando FFmpeg Extração: {' '.join(cmd)}")
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        info(f"Áudio PT-BR extraído com sucesso para: {output_audio.name}")
        return output_audio
    except subprocess.CalledProcessError as exc:
        error(f"Erro ao extrair áudio com ffmpeg. Código: {exc.returncode} | Output: \n{exc.stderr}")
        raise


def mux_audio(file_4k: Path, audio_ptbr: Optional[Path], output_tmp: Path) -> Path:
    """
    Injeta o áudio PT-BR como a primeira faixa no arquivo 4K, preservando o restante,
    ou apenas otimiza o 4K se audio_ptbr for None.
    """
    ffmpeg_path = config.ffmpeg.ffmpeg_path
    allowed_indices = get_allowed_streams(file_4k)

    cmd = [str(ffmpeg_path), "-y", "-i", str(file_4k)]

    if audio_ptbr:
        cmd.extend(["-i", str(audio_ptbr)])

    cmd.extend(["-map", "0:v"])

    if audio_ptbr:
        cmd.extend(["-map", "1:a"])

    for idx in allowed_indices:
        cmd.extend(["-map", f"0:{idx}"])

    cmd.extend(
        [
            "-map_chapters",
            "0",
            "-c",
            "copy",
            "-max_interleave_delta",
            "0",
        ]
    )

    if audio_ptbr:
        cmd.extend(
            [
                "-metadata:s:a:0",
                "language=por",
                "-metadata:s:a:0",
                "title=Português (Brasil)",
            ]
        )

    cmd.append(str(output_tmp))

    try:
        debug(f"Processando FFmpeg Mux: {' '.join(cmd)}")
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
        )

        last_log_time = time.time()
        for line in process.stdout:
            if "time=" in line and "bitrate=" in line:
                current_time = time.time()
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
    except Exception as exc:
        error(f"Falha catastrófica no FFmpeg muxing logger: {exc}")
        raise


def replace_original(output_tmp: Path, file_4k: Path) -> None:
    """
    Substitui o arquivo 4K original pelo output final processado.
    """
    if not output_tmp.exists():
        error(f"Substituição abortada: o arquivo temporário {output_tmp.name} gerado não existe.")
        raise FileNotFoundError(f"Arquivo de saída temporário não encontrado: {output_tmp}")

    size_bytes = output_tmp.stat().st_size
    if size_bytes == 0:
        error(f"Substituição abortada: {output_tmp.name} está vazio (0 bytes).")
        raise ValueError("Arquivo temporário gerado pelo muxing resultou em tamanho zerado.")

    retries = 5
    delay = 3

    for attempt in range(1, retries + 1):
        try:
            debug(f"Tentativa de substituição {attempt}/{retries}. Modificando o arquivo original...")
            os.replace(str(output_tmp), str(file_4k))
            info(f"Arquivo 4K original ({file_4k.name}) substituído com sucesso.")
            return
        except PermissionError as exc:
            warning(
                f"PermissionError detectado (Tentativa {attempt}/{retries}): "
                f"aguardando novo retry em {delay}s..."
            )
            if attempt < retries:
                time.sleep(delay)
            else:
                error("Falha contínua ao substituir arquivo original devido a permissions.")
                raise exc
        except OSError as exc:
            error(f"Erro crítico de I/O ao tentar substituir o arquivo final: {exc}")
            raise


def validate_and_replace(output_tmp: Path, file_4k: Path) -> dict:
    """
    Valida o arquivo final antes de substituir o original.
    """
    validation = validate_final_file(output_tmp, file_4k)
    if not validation.get("valid"):
        reason = validation.get("reason", "UNKNOWN_VALIDATION_FAILURE")
        error(f"Validação final falhou antes do replace_original: {reason}")
        raise ValueError(f"FINAL_VALIDATION_FAILED:{reason}")

    replace_original(output_tmp, file_4k)
    return validation
