import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import src.analyzer as analyzer
import src.audio_fingerprint as audio_fingerprint
import src.merger as merger
import src.qbit_client as qbit_client
import src.radarr_client as radarr_client
from src.config import get_config
from src.history_manager import HistoryManager
from src.notifier import debug, error, info, notify_status, send_progress_update, warning
from src.queue_manager import QueueManager
from src.sync_intelligence import GroupHistoryManager, parse_release_metadata

config = get_config()
BASE_DIR = Path(__file__).resolve().parent.parent
queue_manager = QueueManager(BASE_DIR / config.processing.queue_file, max_attempts=config.processing.max_attempts)
history_manager = HistoryManager(
    BASE_DIR / config.logging.history_file,
    max_entries=getattr(config.logging, "history_max_entries", 500),
)
group_history_manager = GroupHistoryManager(
    BASE_DIR / config.logging.group_history_file,
    max_entries=getattr(config.logging, "group_history_max_entries", 1000),
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


def _resolve_qbit_completed_file(qbit_hash: str | None, qbit_path: str | None) -> Path | None:
    torrent_status = qbit_client.get_torrent_debug_status(qbit_hash or "")
    if torrent_status:
        content_path = torrent_status.get("content_path")
        if content_path:
            content_obj = Path(content_path)
            if content_obj.exists():
                if content_obj.is_file() and content_obj.suffix.lower() == ".mkv":
                    return content_obj
                if content_obj.is_dir():
                    resolved = _get_largest_mkv(content_obj)
                    if resolved:
                        return resolved

    if not qbit_path:
        return None

    path_obj = Path(qbit_path)
    if path_obj.exists():
        if path_obj.is_file() and path_obj.suffix.lower() == ".mkv":
            return path_obj
        if path_obj.is_dir():
            return _get_largest_mkv(path_obj)
    return None


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


def _resolve_manual_context(file_path: Path, tmdb_id: str, title: str, year: str) -> tuple[str, str, str]:
    if tmdb_id:
        return str(tmdb_id), title, year

    movie = radarr_client.get_movie_by_file_path(file_path)
    if not movie:
        return str(tmdb_id), title, year

    resolved_tmdb = str(movie.get("tmdbId") or tmdb_id or "")
    resolved_title = movie.get("title") or title
    resolved_year = str(movie.get("year") or year or "")
    return resolved_tmdb, resolved_title, resolved_year


def _hydrate_context_from_qbit_result(context: dict, add_result: qbit_client.QbitAddResult) -> None:
    if add_result.progress is not None:
        context["progress_percent"] = int(round(float(add_result.progress)))
    if add_result.eta_seconds not in (None, -1):
        context["eta_seconds"] = add_result.eta_seconds
    if add_result.num_seeds is not None:
        context["num_seeds"] = add_result.num_seeds
    if add_result.num_leechs is not None:
        context["num_leechs"] = add_result.num_leechs
    if add_result.state:
        context["qbit_state"] = add_result.state


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
        "group": context.get("group"),
        "source_4k": context.get("source_4k"),
        "source_1080p": context.get("source_1080p"),
        "history_bonus": context.get("history_bonus"),
        "history_reason": context.get("history_reason"),
        "offset_applied": context.get("offset_applied"),
        "offset_applied_seconds": context.get("offset_applied_seconds"),
        "offset_outcome": context.get("offset_outcome"),
        "fingerprint_category": context.get("fingerprint_category"),
        "fingerprint_confidence": context.get("fingerprint_confidence"),
        "fingerprint_offset": context.get("fingerprint_offset"),
        "fingerprint_positions_used": context.get("fingerprint_positions_used"),
        "offset_strategy": context.get("offset_strategy"),
    }
    event.update(extra)
    history_manager.append({key: value for key, value in event.items() if value is not None})


def _update_progress(context: dict, phase: str) -> None:
    message_id = send_progress_update(phase=phase, context=context, message_id=context.get("discord_message_id"))
    if message_id:
        context["discord_message_id"] = message_id


def _status_for_failure(queue_entry: dict, base_status: str) -> str:
    return "ABANDONED" if queue_entry.get("status") == "ABANDONED" else base_status


def _record_group_history(context: dict, result: str, diagnosis_category: str | None = None) -> None:
    group_history_manager.append_attempt(
        {
            "tmdbId": context.get("tmdbId"),
            "release_title": context.get("release_title"),
            "indexer": context.get("indexer"),
            "group": context.get("group", "unknown"),
            "source_4k": context.get("source_4k", "unknown"),
            "source_1080p": context.get("source_1080p", "unknown"),
            "runtime_4k": context.get("runtime_4k"),
            "runtime_1080p": context.get("runtime_1080p"),
            "runtime_oficial": context.get("runtime_oficial"),
            "diagnosis_category": diagnosis_category or context.get("diagnosis_category"),
            "sync_diff": context.get("diff"),
            "offset_estimate": context.get("offset_estimate"),
            "fingerprint_category": context.get("fingerprint_category"),
            "fingerprint_confidence": context.get("fingerprint_confidence"),
            "fingerprint_offset": context.get("fingerprint_offset"),
            "result": result,
        }
    )


def _should_run_fingerprint(diagnosis: dict) -> bool:
    if not getattr(config.fingerprint, "enabled", False):
        return False
    if diagnosis.get("fingerprint_recommended"):
        return True
    return bool(
        getattr(config.fingerprint, "allow_borderline_cut_retry", False)
        and diagnosis.get("category") == "CUT_MISMATCH"
        and float(diagnosis.get("diff") or 0.0) <= float(getattr(config.fingerprint, "max_offset_seconds", 90))
    )


def _normalize_infohash(torrent_hash: str | None) -> str | None:
    if not torrent_hash:
        return None
    normalized = str(torrent_hash).strip().lower()
    return normalized or None


def _remember_infohash(context: dict, torrent_hash: str | None) -> None:
    normalized = _normalize_infohash(torrent_hash)
    if not normalized:
        return
    seen_hashes = context.setdefault("seen_infohashes", [])
    if normalized not in seen_hashes:
        seen_hashes.append(normalized)


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
            if add_result.success:
                remove_failed_candidate()
            if add_result.success:
                remove_failed_candidate()
            if add_result.success:
                remove_failed_candidate()
            if add_result.success:
                remove_failed_candidate()
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
        queue_manager.begin(tmdb_id, "analyzer", candidate_index=0)
        info(f"O filme 4K {title} já possui áudio nativo PT-BR. Iniciando otimização universal...")
        _record_history(context, "SKIPPED_HAS_PTBR", "analyzer")
        _optimize_in_place(file_path, context, is_dry_run)
        context["process_runtime"] = time.perf_counter() - overall_start
        queue_manager.record_success(tmdb_id, "analyzer", candidate_index=0)
        notify_status("SKIPPED_HAS_PTBR", context)
        if context.get("discord_message_id"):
            queue_manager.attach_metadata(tmdb_id, discord_message_id=context["discord_message_id"])
        return

    info(f"O filme 4K {title} não possui áudio nativo PT-BR. Acionando Bypass qBittorrent.")
    candidates = radarr_client.find_best_ptbr_release(tmdb_id)
    if not candidates:
        search_summary = radarr_client.get_last_release_search_summary(tmdb_id) if tmdb_id else {}
        status = "NO_AVAILABLE_SEEDS" if search_summary.get("reason") == "NO_AVAILABLE_SEEDS" else "NOT_FOUND"
        if status == "NO_AVAILABLE_SEEDS":
            warning(f"Nenhum candidato PT-BR com seeds disponÃ­veis foi encontrado para {title}.")
        warning(f"Nenhum candidato Dual Áudio encontrado para {title}. Iniciando otimização universal do original...")
        context["process_runtime"] = time.perf_counter() - overall_start
        _record_history(context, status, "search", search_summary=search_summary or None)
        _optimize_in_place(file_path, context, is_dry_run)
        notify_status("NOT_FOUND", context)
        return

    best = candidates[0]
    context.update(
        {
            "candidate_index": 1,
            "release_title": best.get("title"),
            "indexer": best.get("indexer"),
            "score": best.get("effective_score", best.get("tiebreaker_score")),
            "group": best.get("group"),
            "source_1080p": best.get("source_1080p"),
            "source_4k": best.get("source_4k"),
            "history_bonus": best.get("history_bonus"),
            "history_reason": best.get("history_reason"),
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
    _remember_infohash(context, add_result.torrent_hash)
    _hydrate_context_from_qbit_result(context, add_result)

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
        if context.get("discord_message_id"):
            queue_manager.attach_metadata(tmdb_id, discord_message_id=context.get("discord_message_id"))
        _update_progress(context, "download-await")

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
    _remember_infohash(context, radarr_download_id or context.get("infohash"))
    existing_entry = queue_manager.get_entry(tmdb_id)
    if existing_entry and existing_entry.get("discord_message_id") and not context.get("discord_message_id"):
        context["discord_message_id"] = existing_entry.get("discord_message_id")
    if candidates and current_index < len(candidates):
        candidate = candidates[current_index]
        context.update(
            {
                "candidate_index": current_index + 1,
                "release_title": candidate.get("title"),
                "indexer": candidate.get("indexer"),
                "score": candidate.get("effective_score", candidate.get("tiebreaker_score")),
                "group": candidate.get("group"),
                "source_1080p": candidate.get("source_1080p"),
                "source_4k": candidate.get("source_4k"),
                "history_bonus": candidate.get("history_bonus"),
                "history_reason": candidate.get("history_reason"),
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
    failed_candidate_removed = False

    def mark_stage(stage_name: str, stage_start: float) -> None:
        stage_timings[stage_name] = time.perf_counter() - stage_start

    def remove_failed_candidate() -> None:
        nonlocal failed_candidate_removed
        failed_hash = _normalize_infohash(radarr_download_id or context.get("infohash"))
        if failed_candidate_removed or is_dry_run or not failed_hash:
            return
        try:
            qbit_client.remove_torrent(failed_hash, delete_files=True)
            failed_candidate_removed = True
        except Exception as cleanup_err:
            error(f"WARNING nÃ£o fatal: falha removendo candidato rejeitado do qBittorrent: {cleanup_err}")

    def trigger_fallback(reason_text: str) -> None:
        if not candidates or current_index + 1 >= len(candidates):
            remove_failed_candidate()
            info(f"Fallback acionado por {reason_text}, mas a lista de candidatos jÃ¡ esgotou.")
            return

        seen_hashes = set(context.get("seen_infohashes", []))
        for next_index in range(current_index + 1, len(candidates)):
            next_candidate = candidates[next_index]
            info(f"Fallback acionado por {reason_text}. Tentando candidato #{next_index + 1}: {next_candidate['title']}")
            _record_history(
                context,
                "FALLBACK",
                "fallback",
                fallback_reason=reason_text,
                next_release=next_candidate["title"],
                next_candidate_index=next_index + 1,
            )
            if is_dry_run:
                info(f"[DRY RUN - MERGER] Injetaria o fallback no qBittorrent: {next_candidate['title']}")
                return

            add_result = qbit_client.add_torrent(next_candidate["url"], tmdb_id)
            duplicate_hash = _normalize_infohash(add_result.torrent_hash)
            if duplicate_hash and duplicate_hash in seen_hashes:
                warning(
                    f"Fallback ignorado: candidato #{next_index + 1} resolve para o mesmo infohash jÃ¡ tentado "
                    f"({duplicate_hash[:8]}...)."
                )
                _record_history(
                    context,
                    "SKIPPED_DUPLICATE_CONTENT",
                    "fallback",
                    fallback_reason=reason_text,
                    skipped_release=next_candidate["title"],
                    skipped_infohash=duplicate_hash,
                    skipped_candidate_index=next_index + 1,
                )
                continue

            _remember_infohash(context, add_result.torrent_hash)
            seen_hashes = set(context.get("seen_infohashes", []))

            if add_result.success and add_result.existing and add_result.completed:
                remove_failed_candidate()
                info("Fallback reaproveitou um torrent jÃ¡ concluÃ­do. Continuando o processamento imediatamente.")
                qbit_location = add_result.content_path or add_result.save_path
                if qbit_location:
                    qbit_root = Path(qbit_location)
                    next_path = qbit_root if qbit_root.is_file() else _get_largest_mkv(qbit_root)
                    if next_path:
                        run_merger(
                            next_path,
                            0,
                            tmdb_id,
                            context,
                            is_dry_run,
                            add_result.torrent_hash or "",
                            candidates,
                            next_index,
                        )
                        return
                    warning("Fallback encontrou torrent concluÃ­do, mas nÃ£o foi possÃ­vel resolver o arquivo .mkv.")
                else:
                    warning("Fallback encontrou torrent concluÃ­do, mas o qBittorrent nÃ£o informou o path do conteÃºdo.")
                continue

            if add_result.success:
                remove_failed_candidate()
            return

        info(f"Fallback acionado por {reason_text}, mas todos os candidatos restantes reaproveitam conteÃºdo jÃ¡ tentado.")
        return


    try:
        resolve_start = time.perf_counter()
        original_movie = radarr_client.get_movie_by_tmdbid(tmdb_id)
        _enrich_context_with_movie(context, original_movie)
        runtime_oficial = _runtime_to_seconds(original_movie)
        file_4k = _resolve_4k_file(tmdb_id)
        if not context.get("source_4k") or context.get("source_4k") == "unknown":
            context["source_4k"] = parse_release_metadata(file_4k.name)["source"]
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
                "diagnosis_category": diagnosis.get("category"),
                "auto_offset_eligible": diagnosis.get("auto_offset_eligible"),
                "auto_offset_reason": diagnosis.get("auto_offset_reason"),
                "fingerprint_reason": diagnosis.get("fingerprint_reason"),
            }
        )

        fingerprint_result = None
        if _should_run_fingerprint(diagnosis):
            fingerprint_stage_start = time.perf_counter()
            fingerprint_result = audio_fingerprint.fingerprint_sync(
                file_4k=file_4k,
                file_1080p=file_1080p,
                duration_4k=float(diagnosis.get("runtime_4k") or 0.0),
            )
            mark_stage("fingerprint", fingerprint_stage_start)
            context.update(
                {
                    "fingerprint_category": fingerprint_result.get("category"),
                    "fingerprint_confidence": fingerprint_result.get("confidence"),
                    "fingerprint_offset": fingerprint_result.get("best_offset_seconds"),
                    "fingerprint_positions_used": fingerprint_result.get("positions_used"),
                }
            )

            if fingerprint_result.get("category") == "FINGERPRINT_SYNC_OK":
                diagnosis["sync_ok"] = True
                diagnosis["category"] = "SYNC_OK"
                diagnosis["offset_estimate"] = 0.0
            elif fingerprint_result.get("category") == "FINGERPRINT_OFFSET_OK":
                diagnosis["category"] = "OFFSET_SUSPECTED"
                diagnosis["auto_offset_eligible"] = True
                diagnosis["auto_offset_reason"] = "fingerprint-eligible"
                diagnosis["offset_estimate"] = fingerprint_result.get("best_offset_seconds")
            elif fingerprint_result.get("category") in {"FINGERPRINT_DRIFT_SUSPECTED", "FINGERPRINT_CUT_MISMATCH", "FINGERPRINT_LOW_CONFIDENCE"}:
                diagnosis["sync_ok"] = False
                diagnosis["category"] = fingerprint_result.get("category")
                diagnosis["auto_offset_eligible"] = False
                diagnosis["auto_offset_reason"] = "fingerprint-blocked"
                context["diagnosis_category"] = diagnosis["category"]

        auto_offset_active = bool(diagnosis.get("category") == "OFFSET_SUSPECTED" and diagnosis.get("auto_offset_eligible"))

        if not diagnosis.get("sync_ok") and not auto_offset_active:
            queue_entry = queue_manager.record_failure(
                tmdb_id,
                diagnosis.get("category", "sync"),
                f"sync_failed:{diagnosis.get('category')}",
                candidate_index=current_index,
            )
            context["process_runtime"] = time.perf_counter() - started_at
            base_status = (
                diagnosis.get("category")
                if diagnosis.get("category") in {
                    "SYNC_MISMATCH",
                    "RUNTIME_INCOMPATIBLE",
                    "OFFSET_SUSPECTED",
                    "FINGERPRINT_DRIFT_SUSPECTED",
                    "FINGERPRINT_CUT_MISMATCH",
                    "FINGERPRINT_LOW_CONFIDENCE",
                }
                else "SYNC_MISMATCH"
            )
            status = _status_for_failure(queue_entry, base_status)
            notify_status(status, {**context, "diff": diagnosis.get("diff")})
            _record_history(
                context,
                status,
                "sync",
                sync_category=diagnosis.get("category"),
                fingerprint_category=context.get("fingerprint_category"),
                fingerprint_confidence=context.get("fingerprint_confidence"),
            )
            _record_group_history(context, diagnosis.get("category", status), diagnosis_category=diagnosis.get("category"))
            if status != "ABANDONED":
                trigger_fallback(diagnosis.get("category", "SYNC_MISMATCH"))
            else:
                remove_failed_candidate()
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
            _record_group_history(context, "NOT_FOUND_STREAM", diagnosis_category=diagnosis.get("category"))
            if status != "ABANDONED":
                trigger_fallback("NOT_FOUND_STREAM")
            else:
                remove_failed_candidate()
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
        offset_seconds = None
        if auto_offset_active:
            offset_seconds = float(diagnosis.get("offset_estimate") or 0.0)
            context["offset_applied"] = True
            context["offset_applied_seconds"] = offset_seconds
            context["offset_outcome"] = "attempting"
            context["offset_strategy"] = "fingerprint" if context.get("fingerprint_category") == "FINGERPRINT_OFFSET_OK" else "heuristic"
        else:
            context["offset_applied"] = False
            context["offset_strategy"] = "none"
        if is_dry_run:
            allowed_indices = analyzer.get_allowed_streams(file_4k)
            map_args = " ".join([f"-map 0:{idx}" for idx in allowed_indices])
            ffmpeg_cmd_mux = (
                f"{config.ffmpeg.ffmpeg_path} -y -i {file_4k.name} -i {audio_ptbr.name} "
                f"-map 0:v -map 1:a {map_args} -map_chapters 0 -c copy -max_interleave_delta 0 {output_tmp.name}"
            )
            if offset_seconds not in (None, 0.0):
                ffmpeg_cmd_mux = (
                    f"{config.ffmpeg.ffmpeg_path} -y -i {file_4k.name} -itsoffset {offset_seconds:.3f} -i {audio_ptbr.name} "
                    f"-map 0:v -map 1:a {map_args} -map_chapters 0 -c copy -max_interleave_delta 0 {output_tmp.name}"
                )
            info(f"   M -> {ffmpeg_cmd_mux}")
        else:
            _update_progress(context, "mux")
            try:
                merger.mux_audio(file_4k, audio_ptbr, output_tmp, audio_offset_seconds=offset_seconds)
            except Exception as offset_err:
                if auto_offset_active:
                    queue_entry = queue_manager.record_failure(
                        tmdb_id,
                        "offset-auto",
                        f"offset_failed:{offset_err}",
                        candidate_index=current_index,
                    )
                    context["process_runtime"] = time.perf_counter() - started_at
                    context["offset_outcome"] = "failed"
                    status = _status_for_failure(queue_entry, "OFFSET_SUSPECTED_FAILED")
                    notify_status(status, {**context, "error": str(offset_err)})
                    _record_history(
                        context,
                        status,
                        "offset-mux",
                        error=str(offset_err),
                        auto_offset_reason=diagnosis.get("auto_offset_reason"),
                        offset_strategy=context.get("offset_strategy"),
                    )
                    _record_group_history(context, "OFFSET_SUSPECTED_FAILED", diagnosis_category=diagnosis.get("category"))
                    if status != "ABANDONED":
                        trigger_fallback("OFFSET_SUSPECTED_FAILED")
                    else:
                        remove_failed_candidate()
                    return
                raise
        mark_stage("mux", mux_start)

        validate_start = time.perf_counter()
        if is_dry_run:
            info(f"[DRY RUN - MERGER] Substituição original prevenida. Substituiria {file_4k.name} por {output_tmp.name}.")
            validation = {"valid": True, "reason": "OK"}
        else:
            _update_progress(context, "validate")
            try:
                validation = merger.validate_and_replace(output_tmp, file_4k)
            except Exception as validation_err:
                if auto_offset_active:
                    queue_entry = queue_manager.record_failure(
                        tmdb_id,
                        "offset-validate",
                        f"offset_validation_failed:{validation_err}",
                        candidate_index=current_index,
                    )
                    context["process_runtime"] = time.perf_counter() - started_at
                    context["offset_outcome"] = "failed"
                    status = _status_for_failure(queue_entry, "OFFSET_SUSPECTED_FAILED")
                    notify_status(status, {**context, "error": str(validation_err)})
                    _record_history(
                        context,
                        status,
                        "offset-validate",
                        error=str(validation_err),
                        auto_offset_reason=diagnosis.get("auto_offset_reason"),
                        offset_strategy=context.get("offset_strategy"),
                    )
                    _record_group_history(context, "OFFSET_SUSPECTED_FAILED", diagnosis_category=diagnosis.get("category"))
                    if status != "ABANDONED":
                        trigger_fallback("OFFSET_SUSPECTED_FAILED")
                    else:
                        remove_failed_candidate()
                    return
                raise
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
        if auto_offset_active:
            context["offset_outcome"] = "success"
        queue_manager.record_success(tmdb_id, "merge", candidate_index=current_index)
        context["process_runtime"] = time.perf_counter() - started_at
        context["validation_reason"] = validation.get("reason")
        info(f"Tempos por etapa: {stage_timings}")
        notify_status("SUCCESS", context)
        if context.get("fingerprint_category") == "FINGERPRINT_SYNC_OK":
            success_status = "FINGERPRINT_SYNC_OK"
        elif context.get("offset_strategy") == "fingerprint":
            success_status = "FINGERPRINT_OFFSET_OK"
        else:
            success_status = "SUCCESS"
        _record_history(context, "SUCCESS", "merge", stage_timings=stage_timings, offset_strategy=context.get("offset_strategy"))
        _record_group_history(context, success_status, diagnosis_category=diagnosis.get("category"))
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

            path_obj = _resolve_qbit_completed_file(args.qbit_hash, args.qbit_path)
            if not path_obj:
                error(
                    "Arquivo .mkv ausente para o torrent concluído do qBittorrent. "
                    f"hash={args.qbit_hash or ''} | path={args.qbit_path or ''}"
                )
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

        tmdb_id, title, year = _resolve_manual_context(Path(file_path), tmdb_id, title, year)
        context = _base_context(tmdb_id, title, year)
        run_analyzer(Path(file_path), tmdb_id, title, year, is_dry_run, "")
    except Exception as exc:
        error(f"[FATAL] Falha não recuperável no trigger: {exc}")
        notify_status("ERROR", {**context, "error": str(exc)})
        sys.exit(1)


if __name__ == "__main__":
    main()
