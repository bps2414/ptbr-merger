import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import src.analyzer as analyzer
import src.merger as merger
import src.qbit_client as qbit_client
import src.radarr_client as radarr_client
from src.config import get_config
from src.history_manager import HistoryManager
from src.notifier import debug, error, info, notify_status, send_progress_update, warning
from src.queue_manager import QueueManager

config = get_config()
BASE_DIR = Path(__file__).resolve().parent.parent
queue_manager = QueueManager(BASE_DIR / config.processing.queue_file, max_attempts=config.processing.max_attempts)
history_manager = HistoryManager(
    BASE_DIR / config.logging.history_file,
    max_entries=getattr(config.logging, "history_max_entries", 500),
)


def parse_args():
    parser = argparse.ArgumentParser(description="PTBRMerger Trigger")
    parser.add_argument("--dry-run", action="store_true", help="Executa o script em modo simulação sem mutações.")
    parser.add_argument("--file-path", type=str, help="Caminho do arquivo de vídeo (manual override).")
    parser.add_argument("--qbit-path", type=str, help="Caminho raiz do download repassado via %%D do qBit.")
    parser.add_argument("--qbit-category", type=str, help="Categoria do torrent repassada via %%L.")
    parser.add_argument("--qbit-tags", type=str, help="Tags delimitadas por vírgula repassadas via %%G.")
    parser.add_argument("--qbit-hash", type=str, help="Info hash do qBittorrent via %%I.")
    return parser.parse_known_args()[0]


def _base_context(tmdb_id: str, title: str, year: str) -> dict:
    return {"tmdbId": str(tmdb_id), "title": title, "year": year}


def _get_largest_mkv(folder_path: Path) -> Path | None:
    if not folder_path.exists() or not folder_path.is_dir():
        return None
    mkv_files = list(folder_path.rglob("*.mkv"))
    if not mkv_files:
        return None
    return max(mkv_files, key=lambda path: path.stat().st_size)


def _resolve_4k_file(tmdb_id: str) -> Path:
    original_movie = radarr_client.get_movie_by_tmdbid(tmdb_id)
    if original_movie and "movieFile" in original_movie and original_movie["movieFile"]:
        return Path(original_movie["movieFile"]["path"])
    if original_movie and "path" in original_movie:
        folder = Path(original_movie["path"])
        mkv_files = list(folder.rglob("*.mkv"))
        if mkv_files:
            return max(mkv_files, key=lambda path: path.stat().st_size)
    raise FileNotFoundError(f"Não foi possível localizar o arquivo 4K original no Radarr (TMDB {tmdb_id}).")


def _runtime_to_seconds(movie: dict | None) -> float | None:
    if not movie:
        return None
    runtime = movie.get("runtime")
    if runtime in (None, "", 0):
        return None
    try:
        runtime_value = float(runtime)
    except (TypeError, ValueError):
        return None
    return runtime_value * 60 if runtime_value < 1000 else runtime_value


def _extract_image_url(movie: dict | None, cover_type: str) -> str | None:
    if not movie:
        return None
    for image in movie.get("images", []) or []:
        if image.get("coverType") != cover_type:
            continue
        for key in ("remoteUrl", "url"):
            value = image.get(key)
            if value:
                return value
    return None


def _enrich_context_with_movie(context: dict, movie: dict | None) -> None:
    if not movie:
        return
    poster_url = _extract_image_url(movie, "poster")
    backdrop_url = _extract_image_url(movie, "fanart")
    if poster_url:
        context["poster_url"] = poster_url
    if backdrop_url:
        context["backdrop_url"] = backdrop_url


def _record_history(context: dict, status: str, phase: str, **extra) -> None:
    event = {
        "tmdbId": context.get("tmdbId"),
        "title": context.get("title"),
        "year": context.get("year"),
        "status": status,
        "phase": phase,
        "candidate_index": context.get("candidate_index"),
        "release_title": context.get("release_title"),
        "indexer": context.get("indexer"),
        "infohash": context.get("infohash"),
        "runtime_4k": context.get("runtime_4k"),
        "runtime_1080p": context.get("runtime_1080p"),
        "runtime_oficial": context.get("runtime_oficial"),
        "sync_diff": context.get("diff"),
        "offset_estimate": context.get("offset_estimate"),
        "process_runtime": context.get("process_runtime"),
    }
    event.update(extra)
    history_manager.append({key: value for key, value in event.items() if value is not None})


def _update_progress(context: dict, phase: str) -> None:
    message_id = send_progress_update(phase=phase, context=context, message_id=context.get("discord_message_id"))
    if message_id:
        context["discord_message_id"] = message_id


def _status_for_failure(queue_entry: dict, base_status: str) -> str:
    return "ABANDONED" if queue_entry.get("status") == "ABANDONED" else base_status


def _optimize_in_place(file_path: Path, context: dict, is_dry_run: bool) -> None:
    output_tmp = file_path.parent / "output_opt_tmp.mkv"

    try:
        if is_dry_run:
            allowed_indices = analyzer.get_allowed_streams(file_path)
            map_args = " ".join([f"-map 0:{idx}" for idx in allowed_indices])
            ffmpeg_cmd = (
                f"{config.ffmpeg.ffmpeg_path} -y -i {file_path.name} -map 0:v {map_args} "
                f"-map_chapters 0 -c copy -max_interleave_delta 0 {output_tmp.name}"
            )
            info("[DRY RUN - OPTIMIZER] Otimização universal simulada:")
            info(f"   CMD -> {ffmpeg_cmd}")
            return

        merger.mux_audio(file_path, None, output_tmp)
        merger.validate_and_replace(output_tmp, file_path)
        info(f"Otimização universal concluída com sucesso para: {file_path.name}")
    except Exception as exc:
        error(f"Erro durante a otimização universal de {file_path.name}: {exc}")
    finally:
        if output_tmp.exists():
            output_tmp.unlink(missing_ok=True)


def run_analyzer(file_path: Path, tmdb_id: str, title: str, year: str, is_dry_run: bool, radarr_download_id: str) -> None:
    context = _base_context(tmdb_id, title, year)
    overall_start = time.perf_counter()
    original_movie = radarr_client.get_movie_by_tmdbid(tmdb_id) if tmdb_id else None
    _enrich_context_with_movie(context, original_movie)
    _update_progress(context, "search")

    if analyzer.has_ptbr_audio(file_path):
        info(f"O filme 4K {title} já possui áudio nativo PT-BR. Iniciando otimização universal...")
        _record_history(context, "SKIPPED_HAS_PTBR", "analyzer")
        _optimize_in_place(file_path, context, is_dry_run)
        notify_status("SKIPPED_HAS_PTBR", context)
        return

    info(f"O filme 4K {title} não possui áudio nativo PT-BR. Acionando Bypass qBittorrent.")
    candidates = radarr_client.find_best_ptbr_release(tmdb_id)
    if not candidates:
        warning(f"Nenhum candidato Dual Áudio encontrado para {title}. Iniciando otimização universal do original...")
        context["process_runtime"] = time.perf_counter() - overall_start
        _record_history(context, "NOT_FOUND", "search")
        _optimize_in_place(file_path, context, is_dry_run)
        notify_status("NOT_FOUND", context)
        return

    best = candidates[0]
    context.update(
        {
            "candidate_index": 1,
            "release_title": best.get("title"),
            "indexer": best.get("indexer"),
            "score": best.get("tiebreaker_score"),
        }
    )
    _record_history(context, "CANDIDATE_SELECTED", "search")

    if is_dry_run:
        info(f"[DRY RUN - BYPASS] Sucesso na busca. Injetaria release no qBittorrent para TMDb {tmdb_id}.")
        return

    _update_progress(context, "inject")
    info("Injetando torrent capturado diretamente no client P2P...")
    add_result = qbit_client.add_torrent(best["url"], tmdb_id)
    context["infohash"] = add_result.torrent_hash

    if not add_result.success:
        context["process_runtime"] = time.perf_counter() - overall_start
        _record_history(context, "ERROR", "inject", error="Falha de injeção direta no P2P.")
        notify_status("ERROR", {**context, "error": "Falha de injeção direta no P2P."})
        return

    context["process_runtime"] = time.perf_counter() - overall_start
    _record_history(context, "TORRENT_INJECTED", "inject", existing=add_result.existing, completed=add_result.completed)
    info("Sucesso! O qBittorrent agora possui autonomia para baixar o áudio e acionar este script retroativamente.")
    if not (add_result.existing and add_result.completed):
        queue_manager.record_pending(tmdb_id, "await-download", candidate_index=0)

    if add_result.existing and add_result.completed:
        info("O torrent PT-BR já existia concluído no qBittorrent. Acionando processamento retroativo imediatamente.")
        qbit_location = add_result.content_path or add_result.save_path
        if qbit_location:
            qbit_root = Path(qbit_location)
            path_obj = qbit_root if qbit_root.is_file() else _get_largest_mkv(qbit_root)
            if path_obj:
                run_merger(path_obj, 0, tmdb_id, context, is_dry_run, add_result.torrent_hash or "", candidates, 0)
                return
            warning("O torrent duplicado foi localizado, mas nenhum arquivo .mkv pôde ser resolvido.")
        else:
            warning("O torrent duplicado foi localizado, mas o qBittorrent não informou o path do conteúdo.")


def run_merger(
    file_path: Path,
    ptbrmerger_movie_id: int,
    tmdb_id: str,
    context: dict,
    is_dry_run: bool,
    radarr_download_id: str,
    candidates: list = None,
    current_index: int = 0,
) -> None:
    del ptbrmerger_movie_id
    file_1080p = file_path
    context = dict(context)
    context["tmdbId"] = str(tmdb_id)
    if candidates and current_index < len(candidates):
        candidate = candidates[current_index]
        context.update(
            {
                "candidate_index": current_index + 1,
                "release_title": candidate.get("title"),
                "indexer": candidate.get("indexer"),
                "score": candidate.get("tiebreaker_score"),
            }
        )

    can_process, reason = queue_manager.can_process(tmdb_id)
    if not can_process:
        if reason == "PROCESSING":
            notify_status("DUPLICATE_CALL", context)
        else:
            info(f"Ignorando nova execução para TMDB {tmdb_id}; ledger já está em estado terminal: {reason}.")
        _record_history(context, reason or "BLOCKED", "guard")
        return

    queue_manager.begin(tmdb_id, "merge", candidate_index=current_index)
    _update_progress(context, "merge-start")

    output_tmp = Path("")
    audio_ptbr = Path("")
    stage_timings: dict[str, float] = {}
    started_at = time.perf_counter()
    should_cleanup_qbit = False
    success = False
    preserve_failed = getattr(config.processing, "preserve_failed_artifacts", True)

    def mark_stage(stage_name: str, stage_start: float) -> None:
        stage_timings[stage_name] = time.perf_counter() - stage_start

    def trigger_fallback(reason_text: str) -> None:
        if candidates and current_index + 1 < len(candidates):
            next_candidate = candidates[current_index + 1]
            info(f"Fallback acionado por {reason_text}. Tentando candidato #{current_index + 2}: {next_candidate['title']}")
            _record_history(context, "FALLBACK", "fallback", fallback_reason=reason_text, next_release=next_candidate["title"])
            if not is_dry_run:
                qbit_client.add_torrent(next_candidate["url"], tmdb_id)
            else:
                info(f"[DRY RUN - MERGER] Injetaria o fallback no qBittorrent: {next_candidate['title']}")
        else:
            info(f"Fallback acionado por {reason_text}, mas a lista de candidatos já esgotou.")

    try:
        resolve_start = time.perf_counter()
        original_movie = radarr_client.get_movie_by_tmdbid(tmdb_id)
        _enrich_context_with_movie(context, original_movie)
        runtime_oficial = _runtime_to_seconds(original_movie)
        file_4k = _resolve_4k_file(tmdb_id)
        output_tmp = file_4k.parent / "output_tmp.mkv"
        audio_ptbr = file_1080p.parent / "audio_ptbr.eac3"
        mark_stage("resolve", resolve_start)

        sync_start = time.perf_counter()
        diagnosis = analyzer.diagnose_sync(file_4k, file_1080p, runtime_oficial=runtime_oficial)
        mark_stage("sync", sync_start)
        context.update(
            {
                "runtime_4k": diagnosis.get("runtime_4k"),
                "runtime_1080p": diagnosis.get("runtime_1080p"),
                "runtime_oficial": diagnosis.get("runtime_oficial"),
                "diff": diagnosis.get("diff"),
                "offset_estimate": diagnosis.get("offset_estimate"),
            }
        )

        if not diagnosis.get("sync_ok"):
            queue_entry = queue_manager.record_failure(
                tmdb_id,
                diagnosis.get("category", "sync"),
                f"sync_failed:{diagnosis.get('category')}",
                candidate_index=current_index,
            )
            context["process_runtime"] = time.perf_counter() - started_at
            base_status = diagnosis.get("category") if diagnosis.get("category") in {"SYNC_MISMATCH", "RUNTIME_INCOMPATIBLE", "OFFSET_SUSPECTED"} else "SYNC_MISMATCH"
            status = _status_for_failure(queue_entry, base_status)
            notify_status(status, {**context, "diff": diagnosis.get("diff")})
            _record_history(context, status, "sync", sync_category=diagnosis.get("category"))
            if status != "ABANDONED":
                trigger_fallback(diagnosis.get("category", "SYNC_MISMATCH"))
            return

        stream_start = time.perf_counter()
        stream_idx = analyzer.get_ptbr_stream_index(file_1080p)
        mark_stage("stream-check", stream_start)
        if stream_idx is None:
            queue_entry = queue_manager.record_failure(tmdb_id, "stream-check", "ptbr_stream_missing", candidate_index=current_index)
            context["process_runtime"] = time.perf_counter() - started_at
            status = _status_for_failure(queue_entry, "NOT_FOUND_STREAM")
            notify_status(status, context)
            _record_history(context, status, "stream-check")
            if status != "ABANDONED":
                trigger_fallback("NOT_FOUND_STREAM")
            return

        extract_start = time.perf_counter()
        if is_dry_run:
            ffmpeg_cmd_extr = f"{config.ffmpeg.ffmpeg_path} -y -i {file_1080p.name} -map 0:{stream_idx} -c:a copy {audio_ptbr.name}"
            info("[DRY RUN - MERGER] Supressão I/O ativada. Comandos simulados de console:")
            info(f"   E -> {ffmpeg_cmd_extr}")
        else:
            _update_progress(context, "extract")
            merger.extract_audio(file_1080p, stream_idx, audio_ptbr)
        mark_stage("extract", extract_start)

        mux_start = time.perf_counter()
        if is_dry_run:
            allowed_indices = analyzer.get_allowed_streams(file_4k)
            map_args = " ".join([f"-map 0:{idx}" for idx in allowed_indices])
            ffmpeg_cmd_mux = (
                f"{config.ffmpeg.ffmpeg_path} -y -i {file_4k.name} -i {audio_ptbr.name} "
                f"-map 0:v -map 1:a {map_args} -map_chapters 0 -c copy -max_interleave_delta 0 {output_tmp.name}"
            )
            info(f"   M -> {ffmpeg_cmd_mux}")
        else:
            _update_progress(context, "mux")
            merger.mux_audio(file_4k, audio_ptbr, output_tmp)
        mark_stage("mux", mux_start)

        validate_start = time.perf_counter()
        if is_dry_run:
            info(f"[DRY RUN - MERGER] Substituição original prevenida. Substituiria {file_4k.name} por {output_tmp.name}.")
            validation = {"valid": True, "reason": "OK"}
        else:
            _update_progress(context, "validate")
            validation = merger.validate_and_replace(output_tmp, file_4k)
        mark_stage("validate_replace", validate_start)

        should_cleanup_qbit = True
        if original_movie:
            rescan_start = time.perf_counter()
            if is_dry_run:
                info(f"[DRY RUN - RADARR] RescanMovie seria acionado para original_id={original_movie.get('id')}")
            else:
                _update_progress(context, "finalize")
                radarr_client.rescan_movie(original_movie.get("id", 0))
                radarr_client.apply_success_tag(original_movie.get("id", 0))
            mark_stage("rescan_tag", rescan_start)

        success = True
        queue_manager.record_success(tmdb_id, "merge", candidate_index=current_index)
        context["process_runtime"] = time.perf_counter() - started_at
        context["validation_reason"] = validation.get("reason")
        info(f"Tempos por etapa: {stage_timings}")
        notify_status("SUCCESS", context)
        _record_history(context, "SUCCESS", "merge", stage_timings=stage_timings)
    except Exception as mux_err:
        queue_entry = queue_manager.record_failure(tmdb_id, "merge", str(mux_err), candidate_index=current_index)
        context["process_runtime"] = time.perf_counter() - started_at
        info(f"Tempos por etapa até a falha: {stage_timings}")
        _record_history(context, queue_entry.get("status", "ERROR"), "merge", error=str(mux_err), stage_timings=stage_timings)
        status = _status_for_failure(queue_entry, "ERROR")
        notify_status(status, {**context, "error": str(mux_err)})
        error(f"Erro transacional interno no módulo Merger ao operar I/O: {mux_err}")
        raise
    finally:
        cleanup_start = time.perf_counter()
        try:
            should_remove_temp = success or not preserve_failed
            if should_remove_temp:
                if str(audio_ptbr) and audio_ptbr.exists():
                    audio_ptbr.unlink(missing_ok=True)
                if str(output_tmp) and output_tmp.exists():
                    output_tmp.unlink(missing_ok=True)
                debug("Purgatório de arquivos temporários finalizou de forma limpa.")
            else:
                warning("Artefatos temporários preservados para diagnóstico por configuração.")
        except Exception as cleanup_err:
            error(f"WARNING não fatal: erro no cleanup de arquivos temporários: {cleanup_err}")
        mark_stage("cleanup", cleanup_start)

        try:
            if is_dry_run:
                info(f"[DRY RUN - CLEANUP QBIT] Deleção do torrent retida simulando hash={radarr_download_id[:8]}...")
            elif should_cleanup_qbit and radarr_download_id:
                qbit_client.remove_torrent(radarr_download_id, delete_files=True)
        except Exception as server_err:
            error(f"WARNING não fatal: falha no cleanup remoto do qBittorrent: {server_err}")


def main() -> None:
    args = parse_args()
    is_dry_run = args.dry_run or str(os.environ.get("PTBRMERGER_DRY_RUN", "")).lower() == "true"

    if is_dry_run:
        info("========== EXECUTANDO MODULO MASTER EM [DRY-RUN] ==========")

    if args.qbit_category:
        if args.qbit_category.lower() == "ptbrmerger":
            info("Recebeu evento OnDownloadComplete diretamente do qBittorrent (Modo 2).")
            tags = [tag.strip() for tag in (args.qbit_tags or "").split(",") if tag.strip()]
            tmdb_id = next((tag.split("-")[-1] for tag in tags if tag.startswith("ptbrmerger-tmdbid-")), None)

            if not tmdb_id:
                error("TMDB ID não foi encontrado na tag do torrent Bypass. O MUX não poderá ser pareado.")
                sys.exit(0)

            path_obj = _get_largest_mkv(Path(args.qbit_path)) if args.qbit_path else None
            if not path_obj:
                error(f"Arquivo .mkv ausente no diretório retornado pelo qBittorrent (%D): {args.qbit_path}")
                sys.exit(0)

            original_movie = radarr_client.get_movie_by_tmdbid(tmdb_id)
            real_title = original_movie.get("title", f"TMDB_{tmdb_id}") if original_movie else f"TMDB_{tmdb_id}"
            real_year = str(original_movie.get("year", "")) if original_movie else ""
            context = _base_context(tmdb_id, real_title, real_year)
            candidates = radarr_client.find_best_ptbr_release(tmdb_id)

            current_index = 0
            if candidates and path_obj:
                for index, candidate in enumerate(candidates):
                    if candidate["title"] in path_obj.parent.name:
                        current_index = index
                        break

            run_merger(path_obj, 0, tmdb_id, context, is_dry_run, args.qbit_hash or "", candidates, current_index)
            return
        sys.exit(0)

    event_type = os.environ.get("radarr_eventtype", "")
    file_path = args.file_path or os.environ.get("radarr_moviefile_path", "")
    tmdb_id = os.environ.get("radarr_movie_tmdbid", "")
    title = os.environ.get("radarr_movie_title", "Desconhecido")
    year = os.environ.get("radarr_movie_year", "")
    is_upgrade = str(os.environ.get("radarr_isupgrade", "")).lower() == "true"
    context = _base_context(tmdb_id, title, year)

    if event_type == "Test":
        info("Evento Dummy (Health Check) despachado pelo Radarr. Test OK.")
        sys.exit(0)

    try:
        if event_type != "Download" and not is_upgrade and not args.file_path:
            debug(f"Event_type inapropriado ignorado: {event_type}.")
            sys.exit(0)

        if not file_path:
            raise ValueError("O Radarr não informou a env radarr_moviefile_path.")

        run_analyzer(Path(file_path), tmdb_id, title, year, is_dry_run, "")
    except Exception as exc:
        error(f"[FATAL] Falha não recuperável no trigger: {exc}")
        notify_status("ERROR", {**context, "error": str(exc)})
        sys.exit(1)


if __name__ == "__main__":
    main()
