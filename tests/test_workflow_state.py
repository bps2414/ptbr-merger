from pathlib import Path

from src.domain.media_workflow import JobStatus, Recipe, WorkflowJob
from src.storage.workflow_state import WorkflowState


def test_workflow_state_creates_default_language_profile(tmp_path: Path):
    state = WorkflowState(tmp_path)

    profiles = state.list_language_profiles()

    assert profiles[0]["id"] == "pt-BR-default"
    assert profiles[0]["preferred_audio_language"] == "pt-BR"


def test_workflow_state_upserts_jobs_and_recipes(tmp_path: Path):
    state = WorkflowState(tmp_path)
    job = WorkflowJob(
        id="job-1",
        workflow_id="preferred-audio-merge",
        status=JobStatus.DONE,
        target_name="target.mkv",
        source_name="source.mkv",
        recipe_id="recipe-1",
        created_at="2026-04-27T00:00:00+00:00",
        updated_at="2026-04-27T00:00:00+00:00",
    )
    recipe = Recipe(
        id="recipe-1",
        job_id="job-1",
        workflow_id="preferred-audio-merge",
        label="Adicionar audio a uma midia",
        target_name="target.mkv",
        source_name="source.mkv",
        output_name="target.preferred.mkv",
        language_profile_id="pt-BR-default",
        sync_summary="Sem offset automatico necessario",
        validation_status="SUCCESS",
        report_path="D:/reports/job-1.report.json",
        output_path="D:/output/target.preferred.mkv",
        created_at="2026-04-27T00:00:00+00:00",
    )

    state.upsert_job(job)
    state.upsert_recipe(recipe)

    assert state.list_jobs()[0]["id"] == "job-1"
    assert state.list_recipes()[0]["id"] == "recipe-1"
    assert state.get_recipe("recipe-1")["target_name"] == "target.mkv"
