import json
from pathlib import Path
from unittest.mock import patch

from src.web import ops
from src.web.server import PLAN_STORE, build_response, default_server_address


def test_default_server_address_binds_to_loopback_only():
    assert default_server_address() == ("127.0.0.1", 8787)


def test_build_response_status_route(tmp_path: Path):
    with patch("src.web.server.ops.build_local_status", return_value={"manual_ready": True}):
        status, headers, body = build_response("GET", "/api/status", b"", tmp_path)

    assert status == 200
    assert headers["Content-Type"] == "application/json; charset=utf-8"
    assert json.loads(body.decode("utf-8")) == {"manual_ready": True}


def test_build_response_settings_route(tmp_path: Path):
    with patch("src.web.server.ops.web_settings", return_value={"theme": {"default": "system"}}):
        status, headers, body = build_response("GET", "/api/settings", b"", tmp_path)

    assert status == 200
    assert headers["Content-Type"] == "application/json; charset=utf-8"
    assert json.loads(body.decode("utf-8")) == {"theme": {"default": "system"}}


def test_build_response_dependencies_routes(tmp_path: Path):
    with patch("src.web.server.ops.dependency_status", return_value={"ready": True}):
        status, headers, body = build_response("GET", "/api/dependencies", b"", tmp_path)

    assert status == 200
    assert json.loads(body.decode("utf-8")) == {"ready": True}

    with patch("src.web.server.ops.start_local_ffmpeg_install", return_value={"status": "RUNNING"}):
        status, headers, body = build_response("POST", "/api/dependencies/install-ffmpeg", b"{}", tmp_path)

    assert status == 200
    assert json.loads(body.decode("utf-8")) == {"status": "RUNNING"}

    with patch("src.web.server.ops.ffmpeg_install_status", return_value={"status": "IDLE"}):
        status, headers, body = build_response("GET", "/api/dependencies/install-status", b"", tmp_path)

    assert status == 200
    assert json.loads(body.decode("utf-8")) == {"status": "IDLE"}


def test_build_response_manual_tool_config_route(tmp_path: Path):
    body = json.dumps({"ffmpeg_path": "ffmpeg.exe", "ffprobe_path": "ffprobe.exe"}).encode("utf-8")
    with patch("src.web.server.ops.use_local_tools", return_value={"status": "SAVED"}) as use_tools:
        status, headers, response = build_response("POST", "/api/dependencies/use-local-tools", body, tmp_path)

    assert status == 200
    assert json.loads(response.decode("utf-8")) == {"status": "SAVED"}
    use_tools.assert_called_once_with("ffmpeg.exe", "ffprobe.exe", tmp_path)


def test_build_response_theme_route(tmp_path: Path):
    body = json.dumps({"theme": "dark"}).encode("utf-8")
    with patch("src.web.server.ops.save_web_theme", return_value={"status": "SAVED", "theme": "dark"}):
        status, headers, response = build_response("POST", "/api/settings/theme", body, tmp_path)

    assert status == 200
    assert json.loads(response.decode("utf-8")) == {"status": "SAVED", "theme": "dark"}


def test_build_response_rejects_unknown_route(tmp_path: Path):
    status, headers, body = build_response("GET", "/api/nope", b"", tmp_path)

    assert status == 404
    assert json.loads(body.decode("utf-8"))["error"] == "Rota não encontrada."


def test_build_response_workflows_route(tmp_path: Path):
    status, headers, body = build_response("GET", "/api/workflows", b"", tmp_path)

    payload = json.loads(body.decode("utf-8"))

    assert status == 200
    assert headers["Content-Type"] == "application/json; charset=utf-8"
    assert payload["workflows"][0]["id"] == "preferred-audio-merge"
    assert payload["workflows"][0]["available"] is True


def test_build_response_jobs_recipes_and_profiles_routes(tmp_path: Path):
    for route in ("/api/jobs", "/api/recipes", "/api/language-profiles"):
        status, headers, body = build_response("GET", route, b"", tmp_path)
        assert status == 200
        assert headers["Content-Type"] == "application/json; charset=utf-8"
        assert json.loads(body.decode("utf-8"))


def test_manual_plan_returns_server_side_plan_id(tmp_path: Path):
    PLAN_STORE.clear()
    with patch("src.web.server.ops.build_preferred_audio_plan", return_value={"ready": True}):
        status, headers, body = build_response("POST", "/api/manual-plan", b"{}", tmp_path)

    payload = json.loads(body.decode("utf-8"))
    assert status == 200
    assert headers["Content-Type"] == "application/json; charset=utf-8"
    assert payload["ready"] is True
    assert payload["plan_id"] in PLAN_STORE


def test_manual_run_rejects_browser_supplied_plan_without_plan_id(tmp_path: Path):
    PLAN_STORE.clear()
    body = json.dumps({"plan": {"ready": True}}).encode("utf-8")

    status, headers, response = build_response("POST", "/api/manual-run", body, tmp_path)

    assert status == 400
    assert headers["Content-Type"] == "application/json; charset=utf-8"
    assert json.loads(response.decode("utf-8"))["status"] == "BLOCKED"


def test_manual_run_uses_cached_plan(tmp_path: Path):
    PLAN_STORE.clear()
    PLAN_STORE["abc"] = {"ready": True, "plan_id": "abc"}
    body = json.dumps({"plan_id": "abc"}).encode("utf-8")

    with patch("src.web.server.ops.run_preferred_audio_plan", return_value={"status": "SUCCESS"}) as run:
        status, headers, response = build_response("POST", "/api/manual-run", body, tmp_path)

    assert status == 200
    assert headers["Content-Type"] == "application/json; charset=utf-8"
    assert json.loads(response.decode("utf-8")) == {"status": "SUCCESS"}
    run.assert_called_once_with({"ready": True, "plan_id": "abc"}, ops.ensure_workspace(tmp_path))


def test_manual_run_returns_json_error_when_execution_raises(tmp_path: Path):
    PLAN_STORE.clear()
    PLAN_STORE["abc"] = {"ready": True, "plan_id": "abc"}
    body = json.dumps({"plan_id": "abc"}).encode("utf-8")

    with patch("src.web.server.ops.run_preferred_audio_plan", side_effect=RuntimeError("ffmpeg failed")):
        status, headers, response = build_response("POST", "/api/manual-run", body, tmp_path)

    assert status == 500
    assert headers["Content-Type"] == "application/json; charset=utf-8"
    assert json.loads(response.decode("utf-8")) == {
        "status": "ERROR",
        "error": "Falha interna ao executar o plano local.",
    }


def test_build_response_support_package_route(tmp_path: Path):
    status, headers, body = build_response("POST", "/api/support-package", b"{}", tmp_path)

    payload = json.loads(body.decode("utf-8"))

    assert status == 200
    assert headers["Content-Type"] == "application/json; charset=utf-8"
    assert payload["status"] == "CREATED"
