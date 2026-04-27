from pathlib import Path
from unittest.mock import patch

from src.web.ops import ensure_workspace
from src.workflows.preferred_audio_merge import build_preferred_audio_plan, run_preferred_audio_plan


def test_build_preferred_audio_plan_includes_sync_review(tmp_path: Path):
    workspace = ensure_workspace(tmp_path)
    target = workspace.input_dir / "target.mkv"
    source = workspace.input_dir / "source.mkv"
    target.write_bytes(b"target")
    source.write_bytes(b"source")

    with patch("src.workflows.preferred_audio_merge.inspect_media_file") as inspect, patch(
        "src.workflows.preferred_audio_merge.analyzer.diagnose_sync"
    ) as diagnose:
        inspect.side_effect = [
            {"exists": True, "path": str(target), "name": "target.mkv", "has_ptbr_audio": False, "streams": []},
            {
                "exists": True,
                "path": str(source),
                "name": "source.mkv",
                "has_ptbr_audio": True,
                "ptbr_stream_index": 2,
                "streams": [],
            },
        ]
        diagnose.return_value = {
            "category": "OFFSET_SUSPECTED",
            "offset_estimate": 1.25,
            "offset_confidence": 0.9,
            "diff": 1.25,
            "auto_offset_eligible": True,
            "auto_offset_reason": "offset-confidence-ok",
        }

        plan = build_preferred_audio_plan(str(target), str(source), "pt-BR-default", workspace)

    assert plan["ready"] is True
    assert plan["workflow_id"] == "preferred-audio-merge"
    assert plan["sync_review"]["status"] == "ok"
    assert plan["sync_review"]["suggested_offset_seconds"] == 1.25
    assert plan["ptbr_stream_index"] == 2


def test_run_preferred_audio_plan_uses_automatic_offset_when_safe(tmp_path: Path):
    workspace = ensure_workspace(tmp_path)
    target = workspace.input_dir / "target.mkv"
    source = workspace.input_dir / "source.mkv"
    output = workspace.output_dir / "target.preferred.mkv"
    target.write_bytes(b"target")
    source.write_bytes(b"source")
    plan = {
        "ready": True,
        "id": "plan-1",
        "workflow_id": "preferred-audio-merge",
        "target": {"path": str(target), "name": "target.mkv"},
        "source": {"path": str(source), "name": "source.mkv"},
        "output_path": str(output),
        "language_profile_id": "pt-BR-default",
        "ptbr_stream_index": 2,
        "sync_review": {
            "status": "ok",
            "suggested_offset_seconds": 1.25,
            "suggested_trim_start_seconds": 0.0,
            "suggested_trim_end_seconds": 0.0,
        },
        "manual_offset_seconds": None,
        "manual_trim_start_seconds": 0.0,
        "manual_trim_end_seconds": 0.0,
        "will_replace_original": False,
    }

    with patch("src.workflows.preferred_audio_merge.analyzer.get_ptbr_stream_index", return_value=2), patch(
        "src.workflows.preferred_audio_merge.merger.extract_audio", return_value=workspace.work_dir / "audio.eac3"
    ), patch("src.workflows.preferred_audio_merge.merger.mux_audio") as mux_audio, patch(
        "src.workflows.preferred_audio_merge.analyzer.validate_final_file", return_value={"valid": True, "reason": "OK"}
    ):
        mux_audio.return_value = output
        result = run_preferred_audio_plan(plan, workspace)

    assert result["status"] == "SUCCESS"
    assert result["recipe_id"]
    mux_audio.assert_called_once()
    assert mux_audio.call_args.kwargs["audio_offset_seconds"] == 1.25
