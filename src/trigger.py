import argparse
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import src.analyzer as analyzer
import src.audio_fingerprint as audio_fingerprint
import src.bazarr_client as bazarr_client
import src.merger as merger
import src.qbit_client as qbit_client
import src.radarr_client as radarr_client
from src.config import get_config
from src.history_manager import HistoryManager
from src.notifier import debug, error, info, notify_status, send_progress_update, warning
from src.queue_manager import QueueManager
from src.retry_queue_manager import RetryQueueManager
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
retry_queue_manager = RetryQueueManager(
    BASE_DIR / config.retry.queue_file,
    retry_delays_hours=getattr(config.retry, "delay_hours", [1, 6, 24]),
    max_attempts=getattr(config.retry, "max_attempts", 3),
)


def parse_args():
    parser = argparse.ArgumentParser(description="PTBRMerger Trigger")
    parser.add_argument("--dry-run", action="store_true", help="Executa o script em modo simulação sem mutações.")
    parser.add_argument("--file-path", type=str, help="Caminho do arquivo de vídeo (manual override).")
    parser.add_argument("--qbit-path", type=str, help="Caminho raiz do download repassado via %%D do qBit.")
    parser.add_argument("--qbit-category", type=str, help="Categoria do torrent repassada via %%L.")
    parser.add_argument("--qbit-tags", type=str, help="Tags delimitadas por vírgula repassadas via %%G.")
    parser.add_argument("--qbit-hash", type=str, help="Info hash do qBittorrent via %%I.")
    parser.add_argument("--retry-pending", action="store_true", help="Processa itens de retry_queue.json já vencidos.")
    parser.add_argument("--manual-recovery", action="store_true", help="Executa tentativa manual/assistida de recovery.")
    parser.add_argument("--tmdb-id", type=str, help="TMDB ID explicito para recovery manual.")
    parser.add_argument("--candidate-index", type=int, help="Indice 1-based do candidato forcado na lista do Radarr.")
    parser.add_argument("--force-offset-seconds", type=float, help="Offset manual em segundos para recovery assistido.")
    parser.add_argument("--trim-start-seconds", type=float, default=0.0, help="Trim manual no inicio do audio PT-BR.")
    parser.add_argument("--trim-end-seconds", type=float, default=0.0, help="Trim manual no fim do audio PT-BR.")
    parser.add_argument("--reuse-last-recovery", action="store_true", help="Reaproveita os ultimos parametros de recovery persistidos.")
    parser.add_argument(
        "--preserve-recovery-artifacts",
        action="store_true",
        help="Preserva artefatos temporarios desta tentativa manual mesmo quando a config global limparia.",
    )
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


def _latest_tmdb_event(tmdb_id: str) -> dict:
    for event in reversed(history_manager._read()):
        if str(event.get("tmdbId") or "") == str(tmdb_id):
            return event
    return {}


def _resolve_candidate_index(candidates: list | None, requested_index: int | None, source_path: Path | None) -> int:
    if requested_index is not None and requested_index > 0:
        return requested_index - 1

    if candidates and source_path:
        source_name = source_path.name
        source_parent = source_path.parent.name
        for index, candidate in enumerate(candidates):
            title = str(candidate.get("title") or "")
            if title and (title in source_name or title in source_parent):
                return index

    return 0


def _build_manual_request(args: argparse.Namespace, tmdb_id: str, source_path: Path, current_index: int) -> dict:
    queue_entry = queue_manager.get_entry(tmdb_id) or {}
    latest_event = _latest_tmdb_event(tmdb_id)
    request = {
        "enabled": True,
        "manual_recovery": True,
        "manual_request_id": f"manual-{tmdb_id}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        "manual_candidate_index": current_index + 1,
        "manual_force_offset_seconds": args.force_offset_seconds,
        "manual_trim_start_seconds": float(args.trim_start_seconds or 0.0),
        "manual_trim_end_seconds": float(args.trim_end_seconds or 0.0),
        "manual_reuse_last_recovery": bool(args.reuse_last_recovery),
        "manual_preserve_artifacts": bool(
            args.preserve_recovery_artifacts or getattr(config.processing, "preserve_failed_artifacts", True)
        ),
        "manual_source_path": str(source_path),
    }

    if args.reuse_last_recovery:
        request["manual_force_offset_seconds"] = (
            request.get("manual_force_offset_seconds")
            if request.get("manual_force_offset_seconds") is not None
            else queue_entry.get("manual_force_offset_seconds")
            if queue_entry.get("manual_force_offset_seconds") is not None
            else latest_event.get("manual_force_offset_seconds")
            if latest_event.get("manual_force_offset_seconds") is not None
            else latest_event.get("offset_applied_seconds")
        )
        request["manual_trim_start_seconds"] = float(
            request.get("manual_trim_start_seconds")
            or queue_entry.get("manual_trim_start_seconds")
            or latest_event.get("manual_trim_start_seconds")
            or latest_event.get("recovery_trim_start_seconds")
            or 0.0
        )
        request["manual_trim_end_seconds"] = float(
            request.get("manual_trim_end_seconds")
            or queue_entry.get("manual_trim_end_seconds")
            or latest_event.get("manual_trim_end_seconds")
            or latest_event.get("recovery_trim_end_seconds")
            or 0.0
        )

        if (
            request.get("manual_force_offset_seconds") is None
            and request.get("manual_trim_start_seconds", 0.0) <= 0.0
            and request.get("manual_trim_end_seconds", 0.0) <= 0.0
        ):
            raise ValueError("Nenhuma tentativa anterior com parametros reaproveitaveis foi encontrada para este TMDB.")

    return request


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
        "precheck_result": context.get("precheck_result"),
        "precheck_reason": context.get("precheck_reason"),
        "offset_applied": context.get("offset_applied"),
        "offset_applied_seconds": context.get("offset_applied_seconds"),
        "offset_outcome": context.get("offset_outcome"),
        "fingerprint_category": context.get("fingerprint_category"),
        "fingerprint_confidence": context.get("fingerprint_confidence"),
        "fingerprint_offset": context.get("fingerprint_offset"),
        "fingerprint_positions_used": context.get("fingerprint_positions_used"),
        "offset_strategy": context.get("offset_strategy"),
        "manual_recovery": context.get("manual_recovery"),
        "manual_request_id": context.get("manual_request_id"),
        "manual_candidate_index": context.get("manual_candidate_index"),
        "manual_force_offset_seconds": context.get("manual_force_offset_seconds"),
        "manual_trim_start_seconds": context.get("manual_trim_start_seconds"),
        "manual_trim_end_seconds": context.get("manual_trim_end_seconds"),
        "manual_reuse_last_recovery": context.get("manual_reuse_last_recovery"),
        "manual_preserve_artifacts": context.get("manual_preserve_artifacts"),
        "manual_source_path": context.get("manual_source_path"),
        "retry_reason": context.get("retry_reason"),
        "retry_scheduled_at": context.get("retry_scheduled_at"),
        "bazarr_status": context.get("bazarr_status"),
        "bazarr_available": context.get("bazarr_available"),
    }
    event.update(extra)
    history_manager.append({key: value for key, value in event.items() if value is not None})


def _update_progress(context: dict, phase: str) -> None:
    message_id = send_progress_update(phase=phase, context=context, message_id=context.get("discord_message_id"))
    if message_id:
        context["discord_message_id"] = message_id


def _status_for_failure(queue_entry: dict, base_status: str) -> str:
    return "ABANDONED" if queue_entry.get("status") == "ABANDONED" else base_status


def _schedule_retry_if_eligible(status: str, context: dict, **metadata) -> None:
    if not getattr(config.retry, "enabled", True):
        return
    retryable_statuses = {"NOT_FOUND", "NO_AVAILABLE_SEEDS", "FINGERPRINT_LOW_CONFIDENCE", "OFFSET_SUSPECTED_FAILED"}
    if status not in retryable_statuses:
        return
    retry_entry = retry_queue_manager.schedule_retry(
        context["tmdbId"],
        status,
        metadata={
            "title": context.get("title"),
            "year": context.get("year"),
            "last_release_title": context.get("release_title"),
            **metadata,
        },
    )
    context["retry_scheduled_at"] = retry_entry.get("next_retry_at")
    context["retry_reason"] = status


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
            "recovery_strategy": context.get("recovery_strategy"),
            "recovery_outcome": context.get("recovery_outcome"),
            "recovery_validation_reason": context.get("recovery_validation_reason"),
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


def _update_sync_context(context: dict, diagnosis: dict) -> None:
    context.update(
        {
            "runtime_4k": diagnosis.get("runtime_4k"),
            "runtime_1080p": diagnosis.get("runtime_1080p"),
            "runtime_oficial": diagnosis.get("runtime_oficial"),
            "diff": diagnosis.get("diff"),
            "offset_estimate": diagnosis.get("offset_estimate"),
            "diagnosis_category": diagnosis.get("category"),
            "recoverability": diagnosis.get("recoverability"),
            "diagnosis_terminal": diagnosis.get("terminal"),
            "preserve_candidate": diagnosis.get("preserve_candidate"),
            "recovery_reason": diagnosis.get("recovery_reason"),
            "auto_offset_eligible": diagnosis.get("auto_offset_eligible"),
            "auto_offset_reason": diagnosis.get("auto_offset_reason"),
            "fingerprint_reason": diagnosis.get("fingerprint_reason"),
        }
    )


def _apply_fingerprint_result(diagnosis: dict, fingerprint_result: dict) -> dict:
    category = fingerprint_result.get("category")
    if category == "FINGERPRINT_SYNC_OK":
        diagnosis.update(
            {
                "sync_ok": True,
                "category": "SYNC_OK",
                "recoverability": "not-needed",
                "terminal": False,
                "preserve_candidate": False,
                "recovery_reason": "fingerprint-sync-ok",
                "offset_estimate": 0.0,
                "auto_offset_eligible": False,
                "auto_offset_reason": "fingerprint-sync-ok",
                "fingerprint_reason": "fingerprint-sync-ok",
            }
        )
        return diagnosis

    if category == "FINGERPRINT_OFFSET_OK":
        diagnosis.update(
            {
                "sync_ok": False,
                "category": "OFFSET_SUSPECTED",
                "recoverability": "recoverable",
                "terminal": False,
                "preserve_candidate": True,
                "recovery_reason": "fingerprint-offset-confirmed",
                "auto_offset_eligible": True,
                "auto_offset_reason": "fingerprint-eligible",
                "fingerprint_reason": "fingerprint-offset-confirmed",
                "offset_estimate": fingerprint_result.get("best_offset_seconds"),
            }
        )
        return diagnosis

    if category == "FINGERPRINT_LOW_CONFIDENCE":
        if diagnosis.get("category") == "INTRO_OUTRO_DIVERGENCE":
            diagnosis.update(
                {
                    "sync_ok": False,
                    "category": "INTRO_OUTRO_DIVERGENCE",
                    "recoverability": "recoverable",
                    "terminal": False,
                    "preserve_candidate": True,
                    "recovery_reason": "edge-divergence-fingerprint-inconclusive",
                    "auto_offset_eligible": False,
                    "auto_offset_reason": "fingerprint-inconclusive",
                    "fingerprint_reason": "fingerprint-inconclusive-edge",
                }
            )
            return diagnosis
        diagnosis.update(
            {
                "sync_ok": False,
                "category": "AMBIGUOUS_RECOVERABLE",
                "recoverability": "ambiguous",
                "terminal": False,
                "preserve_candidate": True,
                "recovery_reason": "fingerprint-inconclusive",
                "auto_offset_eligible": False,
                "auto_offset_reason": "fingerprint-inconclusive",
                "fingerprint_reason": "fingerprint-inconclusive",
            }
        )
        return diagnosis

    if category in {"FINGERPRINT_DRIFT_SUSPECTED", "FINGERPRINT_CUT_MISMATCH"}:
        diagnosis.update(
            {
                "sync_ok": False,
                "category": category,
                "recoverability": "terminal",
                "terminal": True,
                "preserve_candidate": False,
                "recovery_reason": "fingerprint-terminal",
                "auto_offset_eligible": False,
                "auto_offset_reason": "fingerprint-blocked",
                "fingerprint_reason": "fingerprint-terminal",
            }
        )
        return diagnosis

    return diagnosis


def _should_preserve_diagnosis(diagnosis: dict, auto_offset_active: bool) -> bool:
    return bool(
        not diagnosis.get("sync_ok")
        and not auto_offset_active
        and diagnosis.get("preserve_candidate")
        and not diagnosis.get("terminal")
    )


def _build_recovery_plan(diagnosis: dict, context: dict) -> dict | None:
    recovery_cfg = getattr(config, "recovery", None)
    if recovery_cfg is None or not getattr(recovery_cfg, "enabled", False):
        return None
    if diagnosis.get("terminal") or diagnosis.get("sync_ok"):
        return None

    category = diagnosis.get("category")
    diff = abs(float(diagnosis.get("diff") or 0.0))
    offset_estimate = diagnosis.get("offset_estimate")
    fingerprint_confidence = context.get("fingerprint_confidence")

    if category == "OFFSET_SUSPECTED" and diagnosis.get("auto_offset_eligible") and offset_estimate is not None:
        if abs(float(offset_estimate)) <= float(getattr(recovery_cfg, "max_offset_seconds", 90)):
            return {
                "strategy": "offset",
                "audio_offset_seconds": float(offset_estimate),
                "recoverability": diagnosis.get("recoverability"),
            }

    if category == "INTRO_OUTRO_DIVERGENCE":
        if float(getattr(recovery_cfg, "min_trim_seconds", 3.0)) <= diff <= float(getattr(recovery_cfg, "max_trim_seconds", 180.0)):
            return {
                "strategy": "edge-trim",
                "trim_start_seconds": 0.0,
                "trim_end_seconds": diff,
                "recoverability": diagnosis.get("recoverability"),
            }

    if category == "AMBIGUOUS_RECOVERABLE" and getattr(recovery_cfg, "allow_ambiguous", False):
        if fingerprint_confidence is None or float(fingerprint_confidence) < float(getattr(recovery_cfg, "ambiguous_min_confidence", 0.6)):
            return None
        if float(getattr(recovery_cfg, "min_trim_seconds", 3.0)) <= diff <= float(getattr(recovery_cfg, "max_trim_seconds", 180.0)):
            return {
                "strategy": "edge-trim",
                "trim_start_seconds": 0.0,
                "trim_end_seconds": diff,
                "recoverability": diagnosis.get("recoverability"),
            }

    return None


def _build_manual_recovery_plan(manual_request: dict | None, automatic_plan: dict | None) -> dict | None:
    if not manual_request or not manual_request.get("enabled"):
        return automatic_plan

    force_offset = manual_request.get("manual_force_offset_seconds")
    trim_start = float(manual_request.get("manual_trim_start_seconds") or 0.0)
    trim_end = float(manual_request.get("manual_trim_end_seconds") or 0.0)

    if force_offset is not None:
        return {
            "strategy": "offset",
            "audio_offset_seconds": float(force_offset),
            "recoverability": "manual",
        }

    if trim_start > 0.0 or trim_end > 0.0:
        return {
            "strategy": "edge-trim",
            "trim_start_seconds": trim_start,
            "trim_end_seconds": trim_end,
            "recoverability": "manual",
        }

    return automatic_plan


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
        bazarr_result = bazarr_client.lookup_ptbr_subtitles(tmdb_id, title=title, year=year)
        context["bazarr_status"] = bazarr_result.get("reason")
        context["bazarr_available"] = bazarr_result.get("available")
        _schedule_retry_if_eligible(status, context, search_summary=search_summary or None)
        _record_history(context, status, "search", search_summary=search_summary or None, bazarr_result=bazarr_result)
        _optimize_in_place(file_path, context, is_dry_run)
        notify_status(status, context)
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
            "precheck_result": best.get("precheck_result"),
            "precheck_reason": best.get("precheck_reason"),
        }
    )
    _record_history(context, "CANDIDATE_SELECTED", "search")

    if is_dry_run:
        info(f"[DRY RUN - BYPASS] Sucesso na busca. Injetaria release no qBittorrent para TMDb {tmdb_id}.")
        return

    _update_progress(context, "inject")
    info("Injetando torrent capturado diretamente no client P2P...")
    add_result = qbit_client.add_torrent(best["url"], tmdb_id, known_infohash=best.get("infohash"))
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
    manual_request: dict | None = None,
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
                "precheck_result": candidate.get("precheck_result"),
                "precheck_reason": candidate.get("precheck_reason"),
            }
        )
    if manual_request:
        context.update(
            {
                "manual_recovery": True,
                "manual_request_id": manual_request.get("manual_request_id"),
                "manual_candidate_index": manual_request.get("manual_candidate_index"),
                "manual_force_offset_seconds": manual_request.get("manual_force_offset_seconds"),
                "manual_trim_start_seconds": manual_request.get("manual_trim_start_seconds"),
                "manual_trim_end_seconds": manual_request.get("manual_trim_end_seconds"),
                "manual_reuse_last_recovery": manual_request.get("manual_reuse_last_recovery"),
                "manual_preserve_artifacts": manual_request.get("manual_preserve_artifacts"),
                "manual_source_path": manual_request.get("manual_source_path"),
            }
        )

    can_process, reason = queue_manager.can_process(tmdb_id)
    if manual_request and reason == "ABANDONED":
        can_process = True
    if not can_process:
        if reason == "PROCESSING":
            notify_status("DUPLICATE_CALL", context)
        else:
            info(f"Ignorando nova execução para TMDB {tmdb_id}; ledger já está em estado terminal: {reason}.")
        _record_history(context, reason or "BLOCKED", "guard")
        return

    queue_manager.begin(tmdb_id, "manual-recovery" if manual_request else "merge", candidate_index=current_index)
    if manual_request:
        queue_manager.attach_metadata(
            tmdb_id,
            manual_recovery=True,
            manual_request_id=context.get("manual_request_id"),
            manual_candidate_index=context.get("manual_candidate_index"),
            manual_force_offset_seconds=context.get("manual_force_offset_seconds"),
            manual_trim_start_seconds=context.get("manual_trim_start_seconds"),
            manual_trim_end_seconds=context.get("manual_trim_end_seconds"),
            manual_reuse_last_recovery=context.get("manual_reuse_last_recovery"),
            manual_preserve_artifacts=context.get("manual_preserve_artifacts"),
            manual_source_path=context.get("manual_source_path"),
        )
        notify_status("MANUAL_RECOVERY_RUNNING", context)
        _record_history(context, "MANUAL_RECOVERY_RUNNING", "manual-recovery")
    _update_progress(context, "merge-start")

    output_tmp = Path("")
    audio_ptbr = Path("")
    recovery_audio = Path("")
    stage_timings: dict[str, float] = {}
    started_at = time.perf_counter()
    should_cleanup_qbit = False
    success = False
    preserve_failed = (
        bool(manual_request.get("manual_preserve_artifacts"))
        if manual_request
        else getattr(config.processing, "preserve_failed_artifacts", True)
    )
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

            add_result = qbit_client.add_torrent(
                next_candidate["url"],
                tmdb_id,
                known_infohash=next_candidate.get("infohash"),
            )
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
        _update_sync_context(context, diagnosis)

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

            diagnosis = _apply_fingerprint_result(diagnosis, fingerprint_result)
            _update_sync_context(context, diagnosis)

        automatic_recovery_plan = _build_recovery_plan(diagnosis, context)
        recovery_plan = _build_manual_recovery_plan(manual_request, automatic_recovery_plan)
        auto_offset_active = bool(recovery_plan and recovery_plan.get("strategy") == "offset")
        recovery_active = bool(recovery_plan)
        if recovery_plan:
            context["recovery_strategy"] = recovery_plan.get("strategy")
            context["recovery_recoverability"] = recovery_plan.get("recoverability")
            context["recovery_trim_start_seconds"] = recovery_plan.get("trim_start_seconds")
            context["recovery_trim_end_seconds"] = recovery_plan.get("trim_end_seconds")

        if manual_request and not diagnosis.get("sync_ok") and not recovery_active:
            queue_entry = queue_manager.record_pending(tmdb_id, "manual-recovery", candidate_index=current_index)
            queue_manager.attach_metadata(
                tmdb_id,
                diagnosis_category=diagnosis.get("category"),
                recoverability=diagnosis.get("recoverability"),
                recovery_reason=diagnosis.get("recovery_reason"),
                manual_recovery=True,
                manual_request_id=context.get("manual_request_id"),
                manual_candidate_index=context.get("manual_candidate_index"),
                manual_force_offset_seconds=context.get("manual_force_offset_seconds"),
                manual_trim_start_seconds=context.get("manual_trim_start_seconds"),
                manual_trim_end_seconds=context.get("manual_trim_end_seconds"),
                manual_reuse_last_recovery=context.get("manual_reuse_last_recovery"),
                manual_preserve_artifacts=context.get("manual_preserve_artifacts"),
                manual_source_path=context.get("manual_source_path"),
                fingerprint_category=context.get("fingerprint_category"),
                fingerprint_confidence=context.get("fingerprint_confidence"),
                fingerprint_offset=context.get("fingerprint_offset"),
            )
            context["process_runtime"] = time.perf_counter() - started_at
            context["manual_status"] = "MANUAL_RECOVERY_PENDING"
            notify_status("MANUAL_RECOVERY_PENDING", {**context, "diff": diagnosis.get("diff")})
            _record_history(
                context,
                "MANUAL_RECOVERY_PENDING",
                "manual-recovery",
                queue_status=queue_entry.get("status"),
                sync_category=diagnosis.get("category"),
                recoverability=diagnosis.get("recoverability"),
                recovery_reason=diagnosis.get("recovery_reason"),
            )
            _record_group_history(context, "MANUAL_RECOVERY_PENDING", diagnosis_category=diagnosis.get("category"))
            return

        if _should_preserve_diagnosis(diagnosis, auto_offset_active) and not recovery_active:
            queue_entry = queue_manager.record_pending(tmdb_id, "recoverability", candidate_index=current_index)
            queue_manager.attach_metadata(
                tmdb_id,
                diagnosis_category=diagnosis.get("category"),
                recoverability=diagnosis.get("recoverability"),
                recovery_reason=diagnosis.get("recovery_reason"),
                fingerprint_category=context.get("fingerprint_category"),
                fingerprint_confidence=context.get("fingerprint_confidence"),
                fingerprint_offset=context.get("fingerprint_offset"),
            )
            context["process_runtime"] = time.perf_counter() - started_at
            status = diagnosis.get("category") or "AMBIGUOUS_RECOVERABLE"
            notify_status(status, {**context, "diff": diagnosis.get("diff")})
            _record_history(
                context,
                status,
                "sync",
                queue_status=queue_entry.get("status"),
                sync_category=diagnosis.get("category"),
                recoverability=diagnosis.get("recoverability"),
                recovery_reason=diagnosis.get("recovery_reason"),
                preserved_candidate=True,
                fingerprint_category=context.get("fingerprint_category"),
                fingerprint_confidence=context.get("fingerprint_confidence"),
            )
            _record_group_history(context, status, diagnosis_category=diagnosis.get("category"))
            return

        if not diagnosis.get("sync_ok") and not auto_offset_active and not recovery_active:
            queue_entry = queue_manager.record_failure(
                tmdb_id,
                diagnosis.get("category", "sync"),
                f"sync_failed:{diagnosis.get('category')}",
                candidate_index=current_index,
            )
            context["process_runtime"] = time.perf_counter() - started_at
            base_status = diagnosis.get("category") or "SYNC_MISMATCH"
            status = _status_for_failure(queue_entry, base_status)
            _schedule_retry_if_eligible(status, context)
            notify_status(status, {**context, "diff": diagnosis.get("diff")})
            _record_history(
                context,
                status,
                "sync",
                queue_status=queue_entry.get("status"),
                sync_category=diagnosis.get("category"),
                recoverability=diagnosis.get("recoverability"),
                recovery_reason=diagnosis.get("recovery_reason"),
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
            queue_entry = queue_manager.record_failure(
                tmdb_id,
                "manual-recovery" if manual_request else "stream-check",
                "ptbr_stream_missing",
                candidate_index=current_index,
            )
            context["process_runtime"] = time.perf_counter() - started_at
            status = _status_for_failure(queue_entry, "MANUAL_RECOVERY_FAILED" if manual_request else "NOT_FOUND_STREAM")
            notify_status(status, context)
            _record_history(context, status, "manual-recovery" if manual_request else "stream-check")
            _record_group_history(context, status if manual_request else "NOT_FOUND_STREAM", diagnosis_category=diagnosis.get("category"))
            if status != "ABANDONED" and not manual_request:
                trigger_fallback("NOT_FOUND_STREAM")
            elif status == "ABANDONED":
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
        recovery_audio = audio_ptbr
        if recovery_active:
            context["recovery_outcome"] = "attempting"
        if auto_offset_active:
            offset_seconds = float(recovery_plan.get("audio_offset_seconds") or 0.0)
            context["offset_applied"] = True
            context["offset_applied_seconds"] = offset_seconds
            context["offset_outcome"] = "attempting"
            if manual_request:
                context["offset_strategy"] = "manual"
            else:
                context["offset_strategy"] = "fingerprint" if context.get("fingerprint_category") == "FINGERPRINT_OFFSET_OK" else "heuristic"
        else:
            context["offset_applied"] = False
            context["offset_strategy"] = "none"

        if recovery_active and recovery_plan.get("strategy") == "edge-trim":
            recovery_audio = file_1080p.parent / "audio_ptbr_recovery.eac3"
            context["recovery_trim_start_seconds"] = float(recovery_plan.get("trim_start_seconds") or 0.0)
            context["recovery_trim_end_seconds"] = float(recovery_plan.get("trim_end_seconds") or 0.0)
            if is_dry_run:
                info(
                    f"   R -> {config.ffmpeg.ffmpeg_path} -y -i {audio_ptbr.name} "
                    f"-trim-start {context['recovery_trim_start_seconds']:.3f} "
                    f"-trim-end {context['recovery_trim_end_seconds']:.3f} "
                    f"{recovery_audio.name}"
                )
            else:
                merger.trim_audio_edges(
                    audio_ptbr,
                    recovery_audio,
                    trim_start_seconds=context["recovery_trim_start_seconds"],
                    trim_end_seconds=context["recovery_trim_end_seconds"],
                )
        if is_dry_run:
            allowed_indices = analyzer.get_allowed_streams(file_4k)
            map_args = " ".join([f"-map 0:{idx}" for idx in allowed_indices])
            ffmpeg_cmd_mux = (
                f"{config.ffmpeg.ffmpeg_path} -y -i {file_4k.name} -i {recovery_audio.name} "
                f"-map 0:v -map 1:a {map_args} -map_chapters 0 -c copy -max_interleave_delta 0 {output_tmp.name}"
            )
            if offset_seconds not in (None, 0.0):
                ffmpeg_cmd_mux = (
                    f"{config.ffmpeg.ffmpeg_path} -y -i {file_4k.name} -itsoffset {offset_seconds:.3f} -i {recovery_audio.name} "
                    f"-map 0:v -map 1:a {map_args} -map_chapters 0 -c copy -max_interleave_delta 0 {output_tmp.name}"
                )
            info(f"   M -> {ffmpeg_cmd_mux}")
        else:
            _update_progress(context, "mux")
            try:
                merger.mux_audio(file_4k, recovery_audio, output_tmp, audio_offset_seconds=offset_seconds)
            except Exception as offset_err:
                if recovery_active:
                    queue_entry = queue_manager.record_failure(
                        tmdb_id,
                        "manual-recovery" if manual_request else "recovery-auto",
                        f"recovery_failed:{offset_err}",
                        candidate_index=current_index,
                    )
                    context["process_runtime"] = time.perf_counter() - started_at
                    context["recovery_outcome"] = "failed"
                    if auto_offset_active:
                        context["offset_outcome"] = "failed"
                    if manual_request:
                        base_status = "MANUAL_RECOVERY_FAILED"
                    else:
                        base_status = "OFFSET_SUSPECTED_FAILED" if auto_offset_active else "AUTO_RECOVERY_FAILED"
                    status = _status_for_failure(queue_entry, base_status)
                    _schedule_retry_if_eligible(status, context, error=str(offset_err))
                    notify_status(status, {**context, "error": str(offset_err)})
                    _record_history(
                        context,
                        status,
                        "recovery-mux",
                        error=str(offset_err),
                        auto_offset_reason=diagnosis.get("auto_offset_reason"),
                        offset_strategy=context.get("offset_strategy"),
                        recovery_strategy=context.get("recovery_strategy"),
                    )
                    _record_group_history(context, status, diagnosis_category=diagnosis.get("category"))
                    if status != "ABANDONED" and not manual_request:
                        trigger_fallback(status)
                    elif status == "ABANDONED":
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
                if recovery_active:
                    recovery_validation = analyzer.validate_recovery_attempt(
                        output_tmp,
                        file_4k,
                        diagnosis=diagnosis,
                        strategy=context.get("recovery_strategy"),
                        source_audio_file=audio_ptbr if str(audio_ptbr) else None,
                        recovered_audio_file=recovery_audio if str(recovery_audio) else None,
                        audio_offset_seconds=offset_seconds,
                        fingerprint_category=context.get("fingerprint_category"),
                        trim_start_seconds=float(context.get("recovery_trim_start_seconds") or 0.0),
                        trim_end_seconds=float(context.get("recovery_trim_end_seconds") or 0.0),
                    )
                    context["recovery_validation_reason"] = recovery_validation.get("reason")
                    context["recovery_postcheck_reason"] = recovery_validation.get("postcheck_reason")
                    context["validation_reason"] = recovery_validation.get("reason")
                    if not recovery_validation.get("valid"):
                        raise ValueError(f"RECOVERY_POSTCHECK_FAILED:{recovery_validation.get('reason')}")
                validation = merger.validate_and_replace(output_tmp, file_4k)
            except Exception as validation_err:
                if recovery_active:
                    queue_entry = queue_manager.record_failure(
                        tmdb_id,
                        "manual-recovery" if manual_request else "recovery-validate",
                        f"recovery_validation_failed:{validation_err}",
                        candidate_index=current_index,
                    )
                    context["process_runtime"] = time.perf_counter() - started_at
                    context["recovery_outcome"] = "failed"
                    if auto_offset_active:
                        context["offset_outcome"] = "failed"
                    if not context.get("validation_reason"):
                        context["validation_reason"] = str(validation_err)
                    if manual_request:
                        base_status = "MANUAL_RECOVERY_FAILED"
                    else:
                        base_status = "OFFSET_SUSPECTED_FAILED" if auto_offset_active else "AUTO_RECOVERY_FAILED"
                    status = _status_for_failure(queue_entry, base_status)
                    _schedule_retry_if_eligible(status, context, error=str(validation_err))
                    notify_status(status, {**context, "error": str(validation_err)})
                    _record_history(
                        context,
                        status,
                        "recovery-validate",
                        error=str(validation_err),
                        auto_offset_reason=diagnosis.get("auto_offset_reason"),
                        offset_strategy=context.get("offset_strategy"),
                        recovery_strategy=context.get("recovery_strategy"),
                    )
                    _record_group_history(context, status, diagnosis_category=diagnosis.get("category"))
                    if status != "ABANDONED" and not manual_request:
                        trigger_fallback(status)
                    elif status == "ABANDONED":
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
        if recovery_active:
            context["recovery_outcome"] = "success"
        if auto_offset_active:
            context["offset_outcome"] = "success"
        success_phase = "manual-recovery" if manual_request else "merge"
        queue_manager.record_success(tmdb_id, success_phase, candidate_index=current_index)
        context["process_runtime"] = time.perf_counter() - started_at
        context["validation_reason"] = validation.get("reason")
        info(f"Tempos por etapa: {stage_timings}")
        if manual_request:
            success_status = "MANUAL_RECOVERY_SUCCESS"
            history_status = "MANUAL_RECOVERY_SUCCESS"
            group_result = "MANUAL_RECOVERY_SUCCESS"
        else:
            success_status = "SUCCESS"
            if context.get("fingerprint_category") == "FINGERPRINT_SYNC_OK":
                history_status = "FINGERPRINT_SYNC_OK"
                group_result = "FINGERPRINT_SYNC_OK"
            elif context.get("offset_strategy") == "fingerprint":
                history_status = "FINGERPRINT_OFFSET_OK"
                group_result = "FINGERPRINT_OFFSET_OK"
            else:
                history_status = "SUCCESS"
                group_result = "SUCCESS"
        notify_status(success_status, context)
        _record_history(
            context,
            history_status,
            success_phase,
            stage_timings=stage_timings,
            offset_strategy=context.get("offset_strategy"),
            recovery_strategy=context.get("recovery_strategy"),
        )
        _record_group_history(context, group_result, diagnosis_category=diagnosis.get("category"))
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
                if str(recovery_audio) and recovery_audio != audio_ptbr and recovery_audio.exists():
                    recovery_audio.unlink(missing_ok=True)
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


def process_pending_retries() -> int:
    processed = 0
    for entry in retry_queue_manager.get_due_entries():
        tmdb_id = str(entry.get("tmdbId") or "")
        if not tmdb_id:
            continue
        can_process, _ = queue_manager.can_process(tmdb_id)
        if not can_process:
            continue

        movie = radarr_client.get_movie_by_tmdbid(tmdb_id)
        if not movie or not movie.get("movieFile") or not movie["movieFile"].get("path"):
            retry_queue_manager.bump_retry(tmdb_id)
            continue

        file_path = Path(movie["movieFile"]["path"])
        if not file_path.exists():
            retry_queue_manager.bump_retry(tmdb_id)
            continue

        retry_queue_manager.remove(tmdb_id)
        run_analyzer(
            file_path=file_path,
            tmdb_id=tmdb_id,
            title=movie.get("title") or entry.get("title") or "",
            year=str(movie.get("year") or entry.get("year") or ""),
            is_dry_run=False,
            radarr_download_id="",
        )
        processed += 1

    return processed


def main() -> None:
    args = parse_args()
    is_dry_run = args.dry_run or str(os.environ.get("PTBRMERGER_DRY_RUN", "")).lower() == "true"

    if is_dry_run:
        info("========== EXECUTANDO MODULO MASTER EM [DRY-RUN] ==========")
    else:
        info("========== EXECUTANDO MODULO MASTER ==========")

    if args.retry_pending:
        processed = process_pending_retries()
        info(f"Retries pendentes processados: {processed}")
        return

    if args.manual_recovery:
        tmdb_id = str(args.tmdb_id or "").strip()
        context = _base_context(tmdb_id, f"TMDB_{tmdb_id}" if tmdb_id else "Desconhecido", "")
        try:
            if not tmdb_id:
                raise ValueError("--manual-recovery exige --tmdb-id.")
            if not args.qbit_path:
                raise ValueError("--manual-recovery exige --qbit-path apontando para o candidato 1080p.")

            path_obj = _resolve_qbit_completed_file(args.qbit_hash, args.qbit_path)
            if not path_obj:
                raise FileNotFoundError(
                    "Nao foi possivel localizar o arquivo do candidato manual. "
                    f"hash={args.qbit_hash or ''} | path={args.qbit_path or ''}"
                )

            original_movie = radarr_client.get_movie_by_tmdbid(tmdb_id)
            real_title = original_movie.get("title", f"TMDB_{tmdb_id}") if original_movie else f"TMDB_{tmdb_id}"
            real_year = str(original_movie.get("year", "")) if original_movie else ""
            context = _base_context(tmdb_id, real_title, real_year)
            candidates = radarr_client.find_best_ptbr_release(tmdb_id)
            current_index = _resolve_candidate_index(candidates, args.candidate_index, path_obj)
            if candidates and args.candidate_index and current_index >= len(candidates):
                raise ValueError("--candidate-index excede a quantidade de candidatos retornados pelo Radarr.")

            manual_request = _build_manual_request(args, tmdb_id, path_obj, current_index)
            run_merger(
                path_obj,
                0,
                tmdb_id,
                context,
                is_dry_run,
                args.qbit_hash or "",
                candidates,
                current_index,
                manual_request=manual_request,
            )
            return
        except Exception as exc:
            error(f"[MANUAL RECOVERY] Falha ao iniciar tentativa manual: {exc}")
            notify_status("ERROR", {**context, "error": str(exc)})
            sys.exit(1)

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
