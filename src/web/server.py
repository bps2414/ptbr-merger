from __future__ import annotations

import json
import mimetypes
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from src.web import ops

STATIC_DIR = Path(__file__).resolve().parent / "static"
PLAN_STORE: dict[str, dict] = {}
mimetypes.add_type("application/manifest+json", ".webmanifest")


def default_server_address() -> tuple[str, int]:
    return ("127.0.0.1", 8787)


def _json_response(payload: dict, status: int = 200) -> tuple[int, dict[str, str], bytes]:
    return (
        status,
        {"Content-Type": "application/json; charset=utf-8"},
        json.dumps(payload, ensure_ascii=False).encode("utf-8"),
    )


def _read_json(body: bytes) -> dict:
    if not body:
        return {}
    try:
        payload = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _store_plan(plan: dict) -> dict:
    plan_id = uuid.uuid4().hex
    stored = {**plan, "plan_id": plan_id}
    PLAN_STORE[plan_id] = stored
    return stored


def _static_response(path: str) -> tuple[int, dict[str, str], bytes]:
    relative = "index.html" if path in ("", "/") else path.lstrip("/")
    candidate = (STATIC_DIR / relative).resolve()
    static_root = STATIC_DIR.resolve()
    if static_root not in candidate.parents and candidate != static_root:
        return _json_response({"error": "Caminho inválido."}, status=400)
    if not candidate.exists() or not candidate.is_file():
        return _json_response({"error": "Arquivo estático não encontrado."}, status=404)
    content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
    return 200, {"Content-Type": content_type}, candidate.read_bytes()


def build_response(method: str, raw_path: str, body: bytes, root: Path) -> tuple[int, dict[str, str], bytes]:
    parsed = urlparse(raw_path)
    path = parsed.path
    workspace = ops.ensure_workspace(root)

    if method == "GET" and path == "/api/status":
        return _json_response(ops.build_local_status(root))
    if method == "GET" and path == "/api/settings":
        return _json_response(ops.web_settings(root))
    if method == "GET" and path == "/api/dependencies":
        return _json_response(ops.dependency_status(root))
    if method == "GET" and path == "/api/dependencies/install-status":
        return _json_response(ops.ffmpeg_install_status())
    if method == "GET" and path == "/api/workflows":
        return _json_response({"workflows": ops.list_available_workflows()})
    if method == "GET" and path == "/api/jobs":
        return _json_response({"jobs": ops.list_workflow_jobs(root)})
    if method == "GET" and path == "/api/recipes":
        return _json_response({"recipes": ops.list_workflow_recipes(root)})
    if method == "GET" and path == "/api/language-profiles":
        return _json_response({"profiles": ops.list_language_profiles(root)})
    if method == "GET" and path == "/api/input-files":
        return _json_response({"files": ops.list_input_files(workspace)})
    if method == "POST" and path == "/api/settings/theme":
        payload = _read_json(body)
        return _json_response(ops.save_web_theme(str(payload.get("theme") or "")))
    if method == "POST" and path == "/api/dependencies/install-ffmpeg":
        return _json_response(ops.start_local_ffmpeg_install(root))
    if method == "POST" and path == "/api/dependencies/use-local-tools":
        payload = _read_json(body)
        return _json_response(
            ops.use_local_tools(
                str(payload.get("ffmpeg_path") or ""),
                str(payload.get("ffprobe_path") or ""),
                root,
            )
        )
    if method == "POST" and path == "/api/inspect":
        payload = _read_json(body)
        return _json_response(ops.inspect_media_file(str(payload.get("path") or ""), workspace))
    if method == "POST" and path == "/api/manual-plan":
        payload = _read_json(body)
        plan = ops.build_preferred_audio_plan(
            str(payload.get("target_path") or ""),
            str(payload.get("source_path") or ""),
            str(payload.get("language_profile_id") or "pt-BR-default"),
            workspace,
        )
        return _json_response(_store_plan(plan))
    if method == "POST" and path == "/api/manual-run":
        payload = _read_json(body)
        plan_id = str(payload.get("plan_id") or "")
        plan = PLAN_STORE.get(plan_id)
        if plan is None:
            return _json_response({"status": "BLOCKED", "problems": ["Plano inválido ou expirado. Recrie o plano."]}, status=400)
        try:
            return _json_response(ops.run_preferred_audio_plan(plan, workspace))
        except Exception:
            return _json_response({"status": "ERROR", "error": "Falha interna ao executar o plano local."}, status=500)
    if method == "POST" and path == "/api/open-folder":
        payload = _read_json(body)
        return _json_response(ops.open_workspace_location(str(payload.get("location") or ""), workspace))
    if method == "POST" and path == "/api/support-package":
        return _json_response(ops.build_support_package(workspace))
    if method == "GET" and not path.startswith("/api/"):
        return _static_response(path)
    return _json_response({"error": "Rota não encontrada."}, status=404)


class PTBRMergerHandler(BaseHTTPRequestHandler):
    root_dir = Path.cwd()

    def _send(self, status: int, headers: dict[str, str], body: bytes) -> None:
        self.send_response(status)
        for key, value in headers.items():
            self.send_header(key, value)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        self._send(*build_response("GET", self.path, b"", self.root_dir))

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length) if length else b""
        self._send(*build_response("POST", self.path, body, self.root_dir))


def main() -> None:
    host, port = default_server_address()
    PTBRMergerHandler.root_dir = Path.cwd()
    server = ThreadingHTTPServer((host, port), PTBRMergerHandler)
    url = f"http://{host}:{port}"
    print(f"PTBRMerger local web mode: {url}")
    webbrowser.open(url)
    server.serve_forever()


if __name__ == "__main__":
    main()
