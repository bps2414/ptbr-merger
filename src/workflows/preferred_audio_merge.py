from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import src.analyzer as analyzer
import src.merger as merger
from src.domain.media_workflow import JobStatus, Recipe, WorkflowJob
from src.storage.workflow_state import WorkflowState
from src.web.ops import inspect_media_file


WORKFLOW_ID = "preferred-audio-merge"
WORKFLOW_LABEL = "Adicionar audio a uma midia"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_within(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def _safe_output_path(target: Path, output_dir: Path) -> Path:
    candidate = output_dir / f"{target.stem}.preferred-audio.mkv"
    if not candidate.exists():
        return candidate
    for index in range(2, 100):
        numbered = output_dir / f"{target.stem}.preferred-audio-{index}.mkv"
        if not numbered.exists():
            return numbered
    raise RuntimeError("Nao foi possivel sugerir um nome de saida livre.")


def _sync_review_from_diagnosis(diagnosis: dict) -> dict:
    category = str(diagnosis.get("category") or "UNKNOWN_SYNC_FAILURE")
    auto_ok = bool(diagnosis.get("auto_offset_eligible"))
    status = "ok" if category == "SYNC_OK" or auto_ok else "attention"
    if diagnosis.get("terminal"):
        status = "blocked"
    return {
        "status": status,
        "confidence": float(diagnosis.get("offset_confidence") or 0.0),
        "suggested_offset_seconds": diagnosis.get("offset_estimate") if auto_ok else None,
        "suggested_trim_start_seconds": 0.0,
        "suggested_trim_end_seconds": 0.0,
        "reason": str(diagnosis.get("auto_offset_reason") or category),
        "duration_diff_seconds": float(diagnosis.get("diff") or 0.0),
        "diagnosis_category": category,
    }


def build_preferred_audio_plan(target_path: str, source_path: str, language_profile_id: str, workspace) -> dict:
    target = inspect_media_file(target_path, workspace)
    source = inspect_media_file(source_path, workspace)
    problems: list[str] = []

    if not target.get("exists"):
        problems.append("Arquivo alvo nao encontrado.")
    if not source.get("exists"):
        problems.append("Arquivo fonte nao encontrado.")
    if target.get("exists") and source.get("exists") and target.get("path") == source.get("path"):
        problems.append("Alvo e fonte precisam ser arquivos diferentes.")
    if source.get("exists") and not source.get("has_ptbr_audio"):
        problems.append("A fonte precisa ter audio detectavel no perfil de idioma.")

    sync_review = {
        "status": "blocked",
        "confidence": 0.0,
        "suggested_offset_seconds": None,
        "suggested_trim_start_seconds": 0.0,
        "suggested_trim_end_seconds": 0.0,
        "reason": "inspection-blocked",
        "duration_diff_seconds": 0.0,
        "diagnosis_category": "NOT_EVALUATED",
    }
    if not problems:
        diagnosis = analyzer.diagnose_sync(Path(target["path"]), Path(source["path"]))
        sync_review = _sync_review_from_diagnosis(diagnosis)

    output_path = ""
    if target.get("exists"):
        output_path = str(_safe_output_path(Path(target["path"]), workspace.output_dir))

    return {
        "id": f"plan-{uuid.uuid4().hex}",
        "workflow_id": WORKFLOW_ID,
        "workflow_label": WORKFLOW_LABEL,
        "ready": not problems and sync_review["status"] != "blocked",
        "problems": problems,
        "target": target,
        "source": source,
        "output_path": output_path,
        "language_profile_id": language_profile_id or "pt-BR-default",
        "ptbr_stream_index": source.get("ptbr_stream_index"),
        "sync_review": sync_review,
        "manual_offset_seconds": None,
        "manual_trim_start_seconds": 0.0,
        "manual_trim_end_seconds": 0.0,
        "will_replace_original": False,
    }


def _selected_offset(plan: dict) -> float | None:
    manual = plan.get("manual_offset_seconds")
    if manual not in (None, ""):
        return float(manual)
    suggested = (plan.get("sync_review") or {}).get("suggested_offset_seconds")
    return float(suggested) if suggested not in (None, "") else None


def _run_preflight_checks(plan: dict, workspace) -> list[str]:
    target = Path(plan["target"]["path"])
    source = Path(plan["source"]["path"])
    output_path = Path(plan["output_path"])
    problems = []
    if not target.exists() or not target.is_file():
        problems.append("Arquivo alvo nao encontrado.")
    if not source.exists() or not source.is_file():
        problems.append("Arquivo fonte nao encontrado.")
    if target.exists() and target.suffix.lower() != ".mkv":
        problems.append("Arquivo alvo precisa ser .mkv.")
    if source.exists() and source.suffix.lower() != ".mkv":
        problems.append("Arquivo fonte precisa ser .mkv.")
    if not _is_within(output_path, workspace.output_dir):
        problems.append("A saida precisa ficar dentro da pasta output/.")
    if output_path.exists():
        problems.append("O arquivo de saida ja existe. Recrie o plano para sugerir outro nome.")
    return problems


def run_preferred_audio_plan(plan: dict, workspace) -> dict:
    if not plan.get("ready"):
        return {"status": "BLOCKED", "problems": plan.get("problems", [])}
    if plan.get("will_replace_original"):
        return {"status": "BLOCKED", "problems": ["Substituir original nao e permitido neste workflow."]}

    problems = _run_preflight_checks(plan, workspace)
    if problems:
        return {"status": "BLOCKED", "problems": problems}

    state = WorkflowState(workspace.root)
    job_id = f"job-{uuid.uuid4().hex}"
    recipe_id = f"recipe-{uuid.uuid4().hex}"
    now = _now()
    target = Path(plan["target"]["path"])
    source = Path(plan["source"]["path"])
    output_path = Path(plan["output_path"])
    stream_index = analyzer.get_ptbr_stream_index(source)
    if stream_index is None or int(stream_index) != int(plan.get("ptbr_stream_index", -1)):
        return {"status": "BLOCKED", "problems": ["A faixa de idioma mudou. Recrie o plano."]}

    state.upsert_job(
        WorkflowJob(
            id=job_id,
            workflow_id=WORKFLOW_ID,
            status=JobStatus.RUNNING,
            target_name=target.name,
            source_name=source.name,
            recipe_id=None,
            created_at=now,
            updated_at=now,
        )
    )

    audio_path = workspace.work_dir / f"{job_id}.preferred_audio.eac3"
    extracted = merger.extract_audio(source, int(stream_index), audio_path)
    merger.mux_audio(target, extracted, output_path, audio_offset_seconds=_selected_offset(plan))
    validation = analyzer.validate_final_file(output_path, target)
    status = "SUCCESS" if validation.get("valid") else "VALIDATION_FAILED"

    sync = plan.get("sync_review") or {}
    offset = _selected_offset(plan)
    sync_summary = "Sem offset automatico necessario" if offset in (None, 0.0) else f"Offset aplicado: {offset:.3f}s"
    report = {
        "job_id": job_id,
        "recipe_id": recipe_id,
        "workflow_id": WORKFLOW_ID,
        "status": status,
        "target_name": target.name,
        "source_name": source.name,
        "output_name": output_path.name,
        "language_profile_id": plan.get("language_profile_id"),
        "sync_review": sync,
        "sync_summary": sync_summary,
        "validation": validation,
        "will_replace_original": False,
    }
    report_path = workspace.reports_dir / f"{job_id}.report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    recipe = Recipe(
        id=recipe_id,
        job_id=job_id,
        workflow_id=WORKFLOW_ID,
        label=WORKFLOW_LABEL,
        target_name=target.name,
        source_name=source.name,
        output_name=output_path.name,
        language_profile_id=str(plan.get("language_profile_id") or "pt-BR-default"),
        sync_summary=sync_summary,
        validation_status=status,
        report_path=str(report_path),
        output_path=str(output_path),
        created_at=now,
    )
    state.upsert_recipe(recipe)
    state.upsert_job(
        WorkflowJob(
            id=job_id,
            workflow_id=WORKFLOW_ID,
            status=JobStatus.DONE if status == "SUCCESS" else JobStatus.FAILED,
            target_name=target.name,
            source_name=source.name,
            recipe_id=recipe_id,
            created_at=now,
            updated_at=_now(),
            last_error=None if status == "SUCCESS" else str(validation.get("reason") or status),
        )
    )
    return {
        "status": status,
        "job_id": job_id,
        "recipe_id": recipe_id,
        "output_path": str(output_path),
        "report_path": str(report_path),
        "validation": validation,
    }
