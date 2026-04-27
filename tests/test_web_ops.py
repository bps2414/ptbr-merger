import json
from pathlib import Path
from unittest.mock import patch

from src.web.ops import (
    LocalWorkspace,
    build_local_status,
    build_manual_plan,
    dependency_status,
    ensure_workspace,
    install_local_ffmpeg,
    inspect_media_file,
    list_input_files,
    list_language_profiles,
    list_workflow_jobs,
    list_workflow_recipes,
    resolve_user_path,
    run_manual_plan,
    open_workspace_location,
    save_web_theme,
    start_local_ffmpeg_install,
    use_local_tools,
    web_settings,
)


def test_ensure_workspace_creates_expected_directories(tmp_path: Path):
    workspace = ensure_workspace(tmp_path)

    assert workspace.root == tmp_path
    assert workspace.input_dir == tmp_path / "input"
    assert workspace.output_dir == tmp_path / "output"
    assert workspace.work_dir == tmp_path / "workdir"
    assert workspace.reports_dir == tmp_path / "reports"
    assert workspace.recipes_dir == tmp_path / "recipes"
    assert workspace.logs_dir == tmp_path / "logs"
    for path in (
        workspace.input_dir,
        workspace.output_dir,
        workspace.work_dir,
        workspace.reports_dir,
        workspace.recipes_dir,
        workspace.logs_dir,
    ):
        assert path.exists()
        assert path.is_dir()


def test_resolve_user_path_accepts_input_file_and_rejects_missing_path(tmp_path: Path):
    workspace = ensure_workspace(tmp_path)
    movie = workspace.input_dir / "movie.mkv"
    movie.write_bytes(b"fake")

    resolved = resolve_user_path(str(movie), workspace)

    assert resolved == movie.resolve()
    missing = resolve_user_path(str(workspace.input_dir / "missing.mkv"), workspace)
    assert missing is None


def test_build_local_status_marks_radarr_and_qbit_as_optional(tmp_path: Path):
    preflight = {
        "status": "BLOCKER",
        "checks": [
            {"name": "ffmpeg", "status": "OK", "message": "available"},
            {"name": "ffprobe", "status": "OK", "message": "available"},
            {"name": "radarr", "status": "BLOCKER", "message": "unreachable"},
            {"name": "qbittorrent", "status": "BLOCKER", "message": "login-failed"},
            {"name": "bazarr", "status": "WARN", "message": "disabled-or-missing-config"},
            {"name": "discord", "status": "WARN", "message": "disabled"},
        ],
    }

    with patch("src.web.ops.run_preflight", return_value=preflight):
        status = build_local_status(tmp_path)

    assert status["mode"] == "manual-recovery"
    assert status["manual_ready"] is True
    assert status["automation_ready"] is False
    assert status["summary"] == "Modo manual disponível. Automação externa incompleta."
    assert status["checks"]["radarr"]["required_for_manual"] is False
    assert status["checks"]["qbittorrent"]["required_for_manual"] is False


def test_list_input_files_only_returns_mkv_files(tmp_path: Path):
    workspace = ensure_workspace(tmp_path)
    (workspace.input_dir / "target.mkv").write_bytes(b"a")
    (workspace.input_dir / "source.MKV").write_bytes(b"b")
    (workspace.input_dir / "notes.txt").write_text("ignore", encoding="utf-8")

    files = list_input_files(workspace)

    assert [item["name"] for item in files] == ["source.MKV", "target.mkv"]


def test_web_ops_exposes_default_language_profile(tmp_path: Path):
    profiles = list_language_profiles(tmp_path)

    assert profiles[0]["id"] == "pt-BR-default"
    assert profiles[0]["label"] == "Portugues Brasil"


def test_web_ops_exposes_empty_jobs_and_recipes(tmp_path: Path):
    assert list_workflow_jobs(tmp_path) == []
    assert list_workflow_recipes(tmp_path) == []


def test_inspect_media_file_returns_stream_summary(tmp_path: Path):
    workspace = ensure_workspace(tmp_path)
    movie = workspace.input_dir / "source.mkv"
    movie.write_bytes(b"fake")
    probe = {
        "format": {"duration": "120.5"},
        "streams": [
            {"index": 0, "codec_type": "video", "codec_name": "hevc", "tags": {}},
            {"index": 1, "codec_type": "audio", "codec_name": "eac3", "tags": {"language": "por", "title": "PT-BR"}},
        ],
    }

    with patch("src.web.ops.analyzer._probe_file", return_value=probe):
        payload = inspect_media_file(str(movie), workspace)

    assert payload["exists"] is True
    assert payload["duration_seconds"] == 120.5
    assert payload["has_ptbr_audio"] is True
    assert payload["ptbr_stream_index"] == 1
    assert payload["streams"][1]["language"] == "por"


def test_inspect_media_file_rejects_non_mkv_before_probe(tmp_path: Path):
    workspace = ensure_workspace(tmp_path)
    secretish = tmp_path / "config.yml"
    secretish.write_text("radarr:\n  api_key: hidden\n", encoding="utf-8")

    with patch("src.web.ops.analyzer._probe_file") as probe:
        payload = inspect_media_file(str(secretish), workspace)

    assert payload == {"exists": False, "error": "Selecione um arquivo .mkv."}
    probe.assert_not_called()


def test_inspect_media_file_returns_json_error_when_ffprobe_fails(tmp_path: Path):
    workspace = ensure_workspace(tmp_path)
    movie = workspace.input_dir / "broken.mkv"
    movie.write_bytes(b"not a real mkv")

    with patch("src.web.ops.analyzer._probe_file", side_effect=RuntimeError("ffprobe failed")):
        payload = inspect_media_file(str(movie), workspace)

    assert payload["exists"] is True
    assert payload["name"] == "broken.mkv"
    assert payload["error"] == "Nao foi possivel inspecionar este MKV com ffprobe."


def test_build_manual_plan_requires_source_with_ptbr_audio(tmp_path: Path):
    workspace = ensure_workspace(tmp_path)
    target = workspace.input_dir / "target.mkv"
    source = workspace.input_dir / "source.mkv"
    target.write_bytes(b"target")
    source.write_bytes(b"source")

    with patch("src.web.ops.inspect_media_file") as inspect:
        inspect.side_effect = [
            {"exists": True, "path": str(target), "name": "target.mkv", "has_ptbr_audio": False, "streams": []},
            {"exists": True, "path": str(source), "name": "source.mkv", "has_ptbr_audio": False, "streams": []},
        ]

        plan = build_manual_plan(str(target), str(source), workspace)

    assert plan["ready"] is False
    assert "A fonte precisa ter áudio PT-BR detectável." in plan["problems"]


def test_build_manual_plan_returns_safe_output_path(tmp_path: Path):
    workspace = ensure_workspace(tmp_path)
    target = workspace.input_dir / "target.4k.mkv"
    source = workspace.input_dir / "source.1080p.mkv"
    target.write_bytes(b"target")
    source.write_bytes(b"source")

    with patch("src.web.ops.inspect_media_file") as inspect:
        inspect.side_effect = [
            {"exists": True, "path": str(target), "name": "target.4k.mkv", "has_ptbr_audio": False, "streams": []},
            {
                "exists": True,
                "path": str(source),
                "name": "source.1080p.mkv",
                "has_ptbr_audio": True,
                "ptbr_stream_index": 2,
                "streams": [],
            },
        ]

        plan = build_manual_plan(str(target), str(source), workspace)

    assert plan["ready"] is True
    assert plan["ptbr_stream_index"] == 2
    assert plan["output_path"].endswith("target.4k.ptbrmerger.mkv")
    assert str(workspace.output_dir) in plan["output_path"]
    assert plan["will_replace_original"] is False


def test_build_manual_plan_suggests_unique_output_path_when_default_exists(tmp_path: Path):
    workspace = ensure_workspace(tmp_path)
    target = workspace.input_dir / "target.4k.mkv"
    source = workspace.input_dir / "source.1080p.mkv"
    target.write_bytes(b"target")
    source.write_bytes(b"source")
    (workspace.output_dir / "target.4k.ptbrmerger.mkv").write_bytes(b"existing")

    with patch("src.web.ops.inspect_media_file") as inspect:
        inspect.side_effect = [
            {"exists": True, "path": str(target), "name": "target.4k.mkv", "has_ptbr_audio": False, "streams": []},
            {
                "exists": True,
                "path": str(source),
                "name": "source.1080p.mkv",
                "has_ptbr_audio": True,
                "ptbr_stream_index": 2,
                "streams": [],
            },
        ]

        plan = build_manual_plan(str(target), str(source), workspace)

    assert plan["ready"] is True
    assert plan["output_path"].endswith("target.4k.ptbrmerger-2.mkv")


def test_run_manual_plan_writes_report_and_recipe_without_replacing_original(tmp_path: Path):
    workspace = ensure_workspace(tmp_path)
    target = workspace.input_dir / "target.mkv"
    source = workspace.input_dir / "source.mkv"
    target.write_bytes(b"target")
    source.write_bytes(b"source")

    plan = {
        "ready": True,
        "target": {"path": str(target), "name": "target.mkv"},
        "source": {"path": str(source), "name": "source.mkv"},
        "ptbr_stream_index": 1,
        "output_path": str(workspace.output_dir / "target.ptbrmerger.mkv"),
        "will_replace_original": False,
    }

    with patch("src.web.ops.analyzer.get_ptbr_stream_index", return_value=1):
        with patch("src.web.ops.merger.extract_audio", return_value=workspace.work_dir / "audio_ptbr.eac3") as extract:
            with patch("src.web.ops.merger.mux_audio", return_value=Path(plan["output_path"])) as mux:
                with patch("src.web.ops.analyzer.validate_final_file", return_value={"valid": True, "reason": "OK"}):
                    result = run_manual_plan(plan, workspace)

    assert result["status"] == "SUCCESS"
    assert result["output_path"] == plan["output_path"]
    assert Path(result["report_path"]).exists()
    assert Path(result["recipe_path"]).exists()
    report = json.loads(Path(result["report_path"]).read_text(encoding="utf-8"))
    recipe = json.loads(Path(result["recipe_path"]).read_text(encoding="utf-8"))
    assert report["will_replace_original"] is False
    assert report["target"] == {"name": "target.mkv", "suffix": "mkv"}
    assert report["source"] == {"name": "source.mkv", "suffix": "mkv"}
    assert recipe["privacy"]["contains_media"] is False
    assert recipe["privacy"]["contains_magnet"] is False
    assert recipe["privacy"]["contains_absolute_paths"] is False
    extract.assert_called_once()
    mux.assert_called_once()


def test_run_manual_plan_rejects_output_path_outside_workspace(tmp_path: Path):
    workspace = ensure_workspace(tmp_path)
    target = workspace.input_dir / "target.mkv"
    source = workspace.input_dir / "source.mkv"
    target.write_bytes(b"target")
    source.write_bytes(b"source")

    plan = {
        "ready": True,
        "target": {"path": str(target), "name": "target.mkv"},
        "source": {"path": str(source), "name": "source.mkv"},
        "ptbr_stream_index": 1,
        "output_path": str(tmp_path / "target.mkv"),
        "will_replace_original": False,
    }

    with patch("src.web.ops.merger.extract_audio") as extract:
        result = run_manual_plan(plan, workspace)

    assert result["status"] == "BLOCKED"
    assert "A saída precisa ficar dentro da pasta output/." in result["problems"]
    extract.assert_not_called()


def test_run_manual_plan_rejects_existing_output_file(tmp_path: Path):
    workspace = ensure_workspace(tmp_path)
    target = workspace.input_dir / "target.mkv"
    source = workspace.input_dir / "source.mkv"
    target.write_bytes(b"target")
    source.write_bytes(b"source")
    output = workspace.output_dir / "target.ptbrmerger.mkv"
    output.write_bytes(b"already here")

    plan = {
        "ready": True,
        "target": {"path": str(target), "name": "target.mkv"},
        "source": {"path": str(source), "name": "source.mkv"},
        "ptbr_stream_index": 1,
        "output_path": str(output),
        "will_replace_original": False,
    }

    with patch("src.web.ops.merger.extract_audio") as extract:
        result = run_manual_plan(plan, workspace)

    assert result["status"] == "BLOCKED"
    assert "O arquivo de saída já existe. Recrie o plano para sugerir outro nome." in result["problems"]
    extract.assert_not_called()


def test_run_manual_plan_rejects_non_mkv_plan_paths(tmp_path: Path):
    workspace = ensure_workspace(tmp_path)
    target = workspace.input_dir / "target.txt"
    source = workspace.input_dir / "source.mkv"
    target.write_bytes(b"target")
    source.write_bytes(b"source")

    plan = {
        "ready": True,
        "target": {"path": str(target), "name": "target.txt"},
        "source": {"path": str(source), "name": "source.mkv"},
        "ptbr_stream_index": 1,
        "output_path": str(workspace.output_dir / "target.ptbrmerger.mkv"),
        "will_replace_original": False,
    }

    with patch("src.web.ops.merger.extract_audio") as extract:
        result = run_manual_plan(plan, workspace)

    assert result["status"] == "BLOCKED"
    assert "Arquivo alvo precisa ser .mkv." in result["problems"]
    extract.assert_not_called()


def test_run_manual_plan_rejects_changed_ptbr_stream_index(tmp_path: Path):
    workspace = ensure_workspace(tmp_path)
    target = workspace.input_dir / "target.mkv"
    source = workspace.input_dir / "source.mkv"
    target.write_bytes(b"target")
    source.write_bytes(b"source")

    plan = {
        "ready": True,
        "target": {"path": str(target), "name": "target.mkv"},
        "source": {"path": str(source), "name": "source.mkv"},
        "ptbr_stream_index": 1,
        "output_path": str(workspace.output_dir / "target.ptbrmerger.mkv"),
        "will_replace_original": False,
    }

    with patch("src.web.ops.analyzer.get_ptbr_stream_index", return_value=2):
        with patch("src.web.ops.merger.extract_audio") as extract:
            result = run_manual_plan(plan, workspace)

    assert result["status"] == "BLOCKED"
    assert "O índice PT-BR mudou; recrie o plano antes de executar." in result["problems"]
    extract.assert_not_called()


def test_open_workspace_location_uses_allowlist(tmp_path: Path):
    workspace = ensure_workspace(tmp_path)

    with patch("src.web.ops.webbrowser.open") as browser_open:
        result = open_workspace_location("input", workspace)
        blocked = open_workspace_location("windows", workspace)

    assert result["status"] == "OPENED"
    assert result["location"] == "input"
    assert blocked["status"] == "BLOCKED"
    browser_open.assert_called_once()


def test_web_settings_exposes_safe_workspace_and_dependency_shape(tmp_path: Path):
    with patch("src.web.ops.dependency_status", return_value={"ready": True}):
        settings = web_settings(tmp_path)

    assert settings["theme"]["allowed"] == ["system", "light", "dark"]
    assert settings["workspace"]["input_dir"].endswith("input")
    assert settings["dependencies"] == {"ready": True}


def test_save_web_theme_accepts_known_values_only():
    assert save_web_theme("dark") == {"status": "SAVED", "theme": "dark"}
    assert save_web_theme("purple")["status"] == "BLOCKED"


def test_dependency_status_reports_detected_tool_versions(tmp_path: Path):
    fake_config = type(
        "Config",
        (),
        {"ffmpeg": type("FFMpeg", (), {"ffmpeg_path": "ffmpeg", "ffprobe_path": "ffprobe"})()},
    )()

    with patch("src.web.ops.config_module.get_config", return_value=fake_config):
        with patch("src.web.ops.shutil.which", side_effect=lambda value: f"C:/tools/{value}.exe"):
            with patch("src.web.ops._run_version", return_value={"available": True, "version": "ok"}):
                status = dependency_status(tmp_path)

    assert status["ready"] is True
    assert status["ffmpeg"]["resolved_path"] == "C:/tools/ffmpeg.exe"
    assert status["ffprobe"]["version"] == "ok"
    assert status["safety"]["changes_global_path"] is False


def test_install_local_ffmpeg_blocks_checksum_mismatch(tmp_path: Path):
    def fake_download(url: str, destination: Path, **kwargs) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if url.endswith(".sha256"):
            destination.write_text("0" * 64, encoding="utf-8")
        else:
            destination.write_bytes(b"zip bytes")

    with patch("src.web.ops.dependency_status", return_value={"ready": False}):
        with patch("src.web.ops._download", side_effect=fake_download):
            result = install_local_ffmpeg(tmp_path)

    assert result["status"] == "BLOCKED"
    assert result["error"] == "Checksum SHA256 não confere."


def test_start_local_ffmpeg_install_updates_config_when_local_bins_already_exist(tmp_path: Path):
    workspace = ensure_workspace(tmp_path)
    tools_dir = workspace.root / "tools" / "ffmpeg"
    ffmpeg = tools_dir / "ffmpeg.exe"
    ffprobe = tools_dir / "ffprobe.exe"
    tools_dir.mkdir(parents=True)
    ffmpeg.write_bytes(b"fake")
    ffprobe.write_bytes(b"fake")

    with patch("src.web.ops._run_version", return_value={"available": True, "version": "ok"}):
        with patch("src.web.ops._save_ffmpeg_config") as save:
            result = start_local_ffmpeg_install(tmp_path)

    assert result["status"] == "INSTALLED"
    assert result["ffmpeg_path"] == str(ffmpeg)
    assert result["ffprobe_path"] == str(ffprobe)
    assert result["source"] == "local-existing"
    save.assert_called_once_with(workspace.root, ffmpeg, ffprobe)


def test_use_local_tools_validates_and_saves_paths(tmp_path: Path):
    workspace = ensure_workspace(tmp_path)
    ffmpeg = workspace.input_dir / "ffmpeg.exe"
    ffprobe = workspace.input_dir / "ffprobe.exe"
    ffmpeg.write_bytes(b"fake")
    ffprobe.write_bytes(b"fake")

    with patch("src.web.ops._run_version", return_value={"available": True, "version": "ok"}):
        with patch("src.web.ops._save_ffmpeg_config") as save:
            result = use_local_tools(str(ffmpeg), str(ffprobe), tmp_path)

    assert result["status"] == "SAVED"
    save.assert_called_once_with(workspace.root, ffmpeg.resolve(), ffprobe.resolve())
