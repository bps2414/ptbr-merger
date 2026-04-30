from src.domain.media_workflow import (
    JobStatus,
    OperationPlan,
    Recipe,
    SyncReview,
    WorkflowJob,
    default_language_profile,
)


def test_default_language_profile_is_not_ptbr_hardcoded_in_the_model_name():
    profile = default_language_profile()

    assert profile.id == "pt-BR-default"
    assert profile.label == "Portugues Brasil"
    assert profile.preferred_audio_language == "pt-BR"
    assert profile.accept_dual_audio is True
    assert profile.keep_original_audio is True
    assert profile.priority == "dubbed-first"


def test_workflow_job_serializes_for_json_store():
    job = WorkflowJob(
        id="job-1",
        workflow_id="preferred-audio-merge",
        status=JobStatus.READY_FOR_REVIEW,
        target_name="target.mkv",
        source_name="source.mkv",
        recipe_id="recipe-1",
        created_at="2026-04-27T00:00:00+00:00",
        updated_at="2026-04-27T00:00:00+00:00",
    )

    payload = job.to_dict()

    assert payload["id"] == "job-1"
    assert payload["workflow_id"] == "preferred-audio-merge"
    assert payload["status"] == "ready_for_review"
    assert payload["recipe_id"] == "recipe-1"


def test_operation_plan_carries_sync_review_without_manual_values_by_default():
    sync = SyncReview(
        status="ok",
        confidence=0.88,
        suggested_offset_seconds=1.25,
        suggested_trim_start_seconds=0.0,
        suggested_trim_end_seconds=0.0,
        reason="fingerprint-offset-ok",
        duration_diff_seconds=1.25,
    )
    plan = OperationPlan(
        id="plan-1",
        workflow_id="preferred-audio-merge",
        target_path="D:/input/target.mkv",
        source_path="D:/input/source.mkv",
        output_path="D:/output/target.preferred.mkv",
        language_profile_id="pt-BR-default",
        ptbr_stream_index=2,
        sync_review=sync,
    )

    payload = plan.to_dict()

    assert payload["sync_review"]["status"] == "ok"
    assert payload["sync_review"]["suggested_offset_seconds"] == 1.25
    assert payload["manual_offset_seconds"] is None
    assert payload["will_replace_original"] is False


def test_recipe_uses_safe_user_facing_summary():
    recipe = Recipe(
        id="recipe-1",
        job_id="job-1",
        workflow_id="preferred-audio-merge",
        label="Adicionar audio a uma midia",
        target_name="target.mkv",
        source_name="source.mkv",
        output_name="target.preferred.mkv",
        language_profile_id="pt-BR-default",
        sync_summary="Offset automatico aplicado: 1.250s",
        validation_status="SUCCESS",
        report_path="D:/reports/job-1.report.json",
        output_path="D:/output/target.preferred.mkv",
        created_at="2026-04-27T00:00:00+00:00",
    )

    payload = recipe.to_dict()

    assert payload["label"] == "Adicionar audio a uma midia"
    assert payload["contains_absolute_paths"] is False
    assert payload["output_name"] == "target.preferred.mkv"
