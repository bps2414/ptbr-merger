import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import argparse
from pathlib import Path

from src.config import get_config
from src.notifier import notify_status, info, error, warning, debug

import src.analyzer as analyzer
import src.radarr_client as radarr_client
import src.qbit_client as qbit_client
import src.merger as merger

config = get_config()

def parse_args():
    parser = argparse.ArgumentParser(description="PTBRMerger Trigger")
    parser.add_argument("--dry-run", action="store_true", help="Executa o script em modo simulação sem mutações de disco/API remotas.")
    parser.add_argument("--file-path", type=str, help="Caminho do arquivo de vídeo (manual override).")
    parser.add_argument("--qbit-path", type=str, help="Caminho raiz do download repassado via %%D do qBit.")
    parser.add_argument("--qbit-category", type=str, help="A categoria vinculada ao Torrent repassada via %%L.")
    parser.add_argument("--qbit-tags", type=str, help="Tags delimitadas por virgula repassadas via %%G.")
    parser.add_argument("--qbit-hash", type=str, help="Info hash do qBittorrent via %%I.")
    return parser.parse_known_args()[0]

def _get_largest_mkv(folder_path: Path) -> Path | None:
    if not folder_path.exists() or not folder_path.is_dir():
        return None
    mkv_files = list(folder_path.rglob("*.mkv"))
    if not mkv_files:
        return None
    return max(mkv_files, key=lambda p: p.stat().st_size)

def _resolve_4k_file(tmdb_id: str) -> Path:
    """Busca reverso o root via Radarr API para parear a origin 4K."""
    original_movie = radarr_client.get_movie_by_tmdbid(tmdb_id)
    if original_movie and "movieFile" in original_movie and original_movie["movieFile"]:
        return Path(original_movie["movieFile"]["path"])
    elif original_movie and "path" in original_movie:
        # Fallback vasculhando o root do filme originário
        folder = Path(original_movie["path"])
        mkv_files = list(folder.rglob("*.mkv"))
        if mkv_files:
            return max(mkv_files, key=lambda p: p.stat().st_size)
            
    raise FileNotFoundError(f"Não foi possível localizar dinamicamente o path do arquivo 4K original na API (TMDB {tmdb_id}).")

def run_analyzer(file_path: Path, tmdb_id: str, title: str, year: str, is_dry_run: bool, radarr_download_id: str) -> None:
    """Entry path inicial do 4K baixado normalmente (First On Import Event)."""
    context = {"title": title, "year": year}
    
    if analyzer.has_ptbr_audio(file_path):
        info(f"O filme 4K {title} já possui áudio nativo PT-BR. Iniciando otimização universal...")
        _optimize_in_place(file_path, context, is_dry_run)
        return
        
    info(f"O filme 4K {title} não possui áudio nativo PT-BR. Acionando Bypass qBittorrent.")
    
    candidates = radarr_client.find_best_ptbr_release(tmdb_id)
    if not candidates:
        warning(f"Nenhum candidato Dual Áudio encontrado para {title}. Iniciando otimização universal do arquivo original...")
        _optimize_in_place(file_path, context, is_dry_run)
        notify_status("NOT_FOUND", context)
        return
        
    best = candidates[0]
    release_url = best["url"]
        
    if is_dry_run:
        info(f"[DRY RUN - BYPASS] Sucesso na busca. Injetaria release no qBittorrent para o filme TMDb {tmdb_id}.")
        return

    info("Injetando torrent capturado diretamente no client P2P...")
    add_result = qbit_client.add_torrent(release_url, tmdb_id)
    if add_result.success:
        info("Sucesso! O qBittorrent agora possui autonomia para baixar o áudio e acionar este script retroativamente via Bypass Mode.")
        if add_result.existing and add_result.completed:
            info("O torrent PT-BR já existia concluído no qBittorrent. Acionando o processamento retroativo imediatamente.")
            qbit_location = add_result.content_path or add_result.save_path
            if qbit_location:
                qbit_root = Path(qbit_location)
                path_obj = qbit_root if qbit_root.is_file() else _get_largest_mkv(qbit_root)
                if path_obj:
                    run_merger(path_obj, 0, tmdb_id, context, is_dry_run, add_result.torrent_hash or "", candidates, 0)
                else:
                    warning("O torrent duplicado já concluído foi localizado, mas nenhum arquivo .mkv pôde ser resolvido para o Modo 2.")
            else:
                warning("O torrent duplicado já concluído foi localizado, mas o qBittorrent não informou o path do conteúdo.")
    else:
        notify_status("ERROR", {**context, "error": "Falha de injeção direta no P2P."})

def _optimize_in_place(file_path: Path, context: dict, is_dry_run: bool) -> None:
    """Realiza a otimização de streams (Stream Diet) no próprio arquivo 4K original."""
    output_tmp = file_path.parent / "output_opt_tmp.mkv"
    
    try:
        if is_dry_run:
            from src.analyzer import get_allowed_streams
            allowed_indices = get_allowed_streams(file_path)
            map_args = " ".join([f"-map 0:{idx}" for idx in allowed_indices])
            ffmpeg_cmd = f"{config.ffmpeg.ffmpeg_path} -y -i {file_path.name} -map 0:v {map_args} -map_chapters 0 -c copy -max_interleave_delta 0 {output_tmp.name}"
            info(f"[DRY RUN - OPTIMIZER] Otimização universal simulada:")
            info(f"   CMD -> {ffmpeg_cmd}")
        else:
            merger.mux_audio(file_path, None, output_tmp)
            merger.replace_original(output_tmp, file_path)
            info(f"Otimização universal concluída com sucesso para: {file_path.name}")
            
    except Exception as e:
        error(f"Erro durante a otimização universal de {file_path.name}: {e}")
    finally:
        if output_tmp.exists():
            output_tmp.unlink(missing_ok=True)

def run_merger(file_path: Path, ptbrmerger_movie_id: int, tmdb_id: str, context: dict, is_dry_run: bool, radarr_download_id: str, candidates: list = None, current_index: int = 0) -> None:
    """Entry path secundário disparado restritamente por Mídia do folder/profile ptbrmerger."""
    file_1080p = file_path
    
    # 1. Definição Prévia de Caminhos Temporários (Regra do finally ser blindado de Exceptions)
    output_tmp = Path("")
    audio_ptbr = Path("")
    
    def trigger_fallback(reason: str):
        if candidates and current_index + 1 < len(candidates):
            next_cand = candidates[current_index + 1]
            info(f"Fallback acionado por {reason}. Tentando candidato #{current_index + 2}: {next_cand['title']}")
            if not is_dry_run:
                qbit_client.add_torrent(next_cand['url'], tmdb_id)
            else:
                info(f"[DRY RUN - MERGER] Injetaria o fallback no qBittorrent: {next_cand['title']}")
        else:
            info(f"Fallback acionado por {reason}, mas a lista de candidatos já esgotou.")
    
    try:
        file_4k = _resolve_4k_file(tmdb_id)
        
        output_tmp = file_4k.parent / "output_tmp.mkv"
        audio_ptbr = file_1080p.parent / "audio_ptbr.eac3"
        
        # 2. Sync Validation
        if not analyzer.validate_sync(file_4k, file_1080p):
            diff = abs(analyzer.get_duration(file_4k) - analyzer.get_duration(file_1080p))
            notify_status("SYNC_MISMATCH", {**context, "diff": diff})
            trigger_fallback("SYNC_MISMATCH")
            return
            
        # 3. Codec Track Check
        stream_idx = analyzer.get_ptbr_stream_index(file_1080p)
        if stream_idx is None:
            notify_status("NOT_FOUND_STREAM", context)
            trigger_fallback("NOT_FOUND_STREAM")
            return

        ffmpeg_cmd_extr = f"{config.ffmpeg.ffmpeg_path} -y -i {file_1080p.name} -map 0:{stream_idx} -c:a copy {audio_ptbr.name}"

        # Build dynamic mux cmd for logging
        allowed_indices = analyzer.get_allowed_streams(file_4k)
        map_args = " ".join([f"-map 0:{idx}" for idx in allowed_indices])
        ffmpeg_cmd_mux = f"{config.ffmpeg.ffmpeg_path} -y -i {file_4k.name} -i {audio_ptbr.name} -map 0:v -map 1:a {map_args} -map_chapters 0 -c copy -max_interleave_delta 0 ... {output_tmp.name}"

        # 4. Mix Operation (Dry-Run Guarded)
        if is_dry_run:
            info(f"[DRY RUN - MERGER] Supressão I/O ativada. Comandos simulados de console:")
            info(f"   E -> {ffmpeg_cmd_extr}")
            info(f"   M -> {ffmpeg_cmd_mux}")
            info(f"[DRY RUN - MERGER] Substituição original prevenida. Substituiria {file_4k.name} por {output_tmp.name}.")
        else:
            merger.extract_audio(file_1080p, stream_idx, audio_ptbr)
            merger.mux_audio(file_4k, audio_ptbr, output_tmp)
            merger.replace_original(output_tmp, file_4k)
            
        # 5. Restabelecimento Metadados via Rescan Radarr V3 Original
        original_movie = radarr_client.get_movie_by_tmdbid(tmdb_id)
        if original_movie:
            if is_dry_run:
                info(f"[DRY RUN - RADARR] RescanMovie payload retido em proxy. Original_id afetado seria {original_movie.get('id')}")
            else:
                radarr_client.rescan_movie(original_movie.get("id", 0))

        # 6. Notificação final
        if is_dry_run:
            info("[DRY RUN - WEBHOOK] Processo finalizado simulando sucesso de mix. Disparo retido ao host de log/webhook.")
        else:
            notify_status("SUCCESS", context)

    except Exception as mux_err:
        error(f"Erro transacional interno estourou no módulo Merger ao operar I/O: {mux_err}")
        notify_status("ERROR", {**context, "error": str(mux_err)})
        raise
        
    finally:
        # Purgatório Obrigatório (Limpa disco sempre, independentemente da stack de exceções)
        try:
            if str(audio_ptbr) and audio_ptbr.exists():
                audio_ptbr.unlink(missing_ok=True)
            if str(output_tmp) and output_tmp.exists():
                output_tmp.unlink(missing_ok=True)
            debug("Purgatório de arquivos (.eac3 e temp output) do filesystem finalizou de forma limpa.")
        except Exception as cln_err:
            error(f"WARNING não fatal: Erro no unlink de raw files duranto finally pass: {cln_err}")

        # Finalizações de Remote Host Servarrs
        try:
            if is_dry_run:
                info(f"[DRY RUN - CLEANUP QBIT] Deleção host HTTP do torrent retida simulando hash={radarr_download_id[:8]}...")
            else:
                if radarr_download_id:
                    qbit_client.remove_torrent(radarr_download_id, delete_files=True)
        except Exception as svrr_err:
            error(f"WARNING não fatal: Falha no garbage collector comunicando APIs HTTP no cleanup loop: {svrr_err}")

def main() -> None:
    args = parse_args()
    
    # Avalia flags locais e Envs do Radarr para dry-run
    is_dry_run = args.dry_run or str(os.environ.get("PTBRMERGER_DRY_RUN", "")).lower() == "true"
    
    if is_dry_run:
        info("========== EXECUTANDO MODULO MASTER EM [DRY-RUN] (APENAS LEITURA) ==========")
    
    # 1. Avalia flags do qBittorrent primeiramente (Modo 2 - Bypass Post-Download)
    if args.qbit_category:
        if args.qbit_category.lower() == "ptbrmerger":
            info("Recebeu evento OnDownloadComplete diretamente do qBittorrent (Modo 2).")
            tags_str = args.qbit_tags or ""
            tags = [t.strip() for t in tags_str.split(",")]
            tmdb_id = next((t.split("-")[-1] for t in tags if t.startswith("ptbrmerger-tmdbid-")), None)
            
            if not tmdb_id:
                error("TMDB ID não foi indexado na tag original do torrent Bypass. O MUX não poderá ser pareado.")
                sys.exit(0)
                
            path_obj = _get_largest_mkv(Path(args.qbit_path)) if args.qbit_path else None
            if not path_obj:
                error(f"Arquivo .mkv ausente no diretório retornado pelo qBittorrent (%D): {args.qbit_path}")
                sys.exit(0)
                
            # Repassa a instrução de mesclagem para o fluxo mestre resgatando o 4K da API original do Radarr
            original_movie = radarr_client.get_movie_by_tmdbid(tmdb_id)
            real_title = original_movie.get("title", f"TMDB_{tmdb_id}") if original_movie else f"TMDB_{tmdb_id}"
            real_year = original_movie.get("year", "") if original_movie else ""
            context = {"title": real_title, "year": str(real_year)}
            radarr_download_id = args.qbit_hash or ""
            candidates = radarr_client.find_best_ptbr_release(tmdb_id)
            
            current_index = 0
            if candidates and path_obj:
                for i, c in enumerate(candidates):
                    if c['title'] in path_obj.parent.name:
                        current_index = i
                        break
                        
            run_merger(path_obj, 0, tmdb_id, context, is_dry_run, radarr_download_id, candidates, current_index)
            return
        else:
            # Filme comum no qBittorrent de outra categoria que não é do nosso sistema
            sys.exit(0)
            
    # 2. Parsing massivo da Env Scope original do Radarr (Modo 1)
    event_type = os.environ.get("radarr_eventtype", "")
    file_path = args.file_path or os.environ.get("radarr_moviefile_path", "")
    tmdb_id = os.environ.get("radarr_movie_tmdbid", "")
    title = os.environ.get("radarr_movie_title", "Desconhecido")
    year = os.environ.get("radarr_movie_year", "")
    is_upgrade = str(os.environ.get("radarr_isupgrade", "")).lower() == "true"
    
    context = {"title": title, "year": year}

    if event_type == "Test":
        info("Evento Dummy (Health Check) despachado pelo Radarr. Test OK.")
        sys.exit(0)

    try:
        if event_type != "Download" and not is_upgrade and not args.file_path:
            debug(f"Event_type inapropriado ignorado: {event_type}.")
            sys.exit(0)
            
        if not file_path:
            raise ValueError("O Radarr não informou a env radarr_moviefile_path.")
            
        path_obj = Path(file_path)

        # O Modo 1 invariavelmente age como Porta de Entrada chamando o Analyzer
        run_analyzer(path_obj, tmdb_id, title, year, is_dry_run, "")
            
    except Exception as e:
        # Regra final e fundamental: Nenhuma exceção sai do container try principal sem notificar o webhook remoto
        # e cravar exit(1) em stderr pro log do OS/Radarr
        error(f"[FATAL] Traceback estourou para o wrapper raiz da Orquestração do Trigger. Falha não recuperável: {e}")
        notify_status("ERROR", {**context, "error": str(e)})
        sys.exit(1)

if __name__ == "__main__":
    main()
