import json
import re
from pathlib import Path


def _sanitize_url(value: str) -> str:
    if not value:
        return value
    value = re.sub(r"apikey=[^&]+", "apikey=<redacted>", value, flags=re.IGNORECASE)
    value = re.sub(r"link=[^&]+", "link=<redacted>", value, flags=re.IGNORECASE)
    return value.replace("localhost:9696", "sanitized.local")


def _sanitize_path(value: str) -> str:
    if not value:
        return value
    value = re.sub(r"^[A-Za-z]:\\data\\", r"D:\\media\\", value)
    value = value.replace("/MediaCover/", "/MediaCover/")
    return value


def sanitize_radarr_movie(movie: dict) -> dict:
    payload = json.loads(json.dumps(movie))
    if payload.get("path"):
        payload["path"] = _sanitize_path(payload["path"])
    movie_file = payload.get("movieFile") or {}
    if movie_file.get("path"):
        movie_file["path"] = _sanitize_path(movie_file["path"])
    payload["movieFile"] = movie_file
    for image in payload.get("images") or []:
        if image.get("remoteUrl"):
            image["remoteUrl"] = re.sub(r"/[^/]+\.jpg$", "/" + image["coverType"] + ".jpg", image["remoteUrl"])
    return payload


def sanitize_radarr_release(release: dict) -> dict:
    payload = json.loads(json.dumps(release))
    if payload.get("downloadUrl"):
        payload["downloadUrl"] = _sanitize_url(payload["downloadUrl"])
    if payload.get("magnetUrl"):
        payload["magnetUrl"] = "<redacted-magnet>"
    return payload


def sanitize_qbit_torrent(torrent: dict) -> dict:
    payload = json.loads(json.dumps(torrent))
    for key in ("save_path", "content_path"):
        if payload.get(key):
            payload[key] = _sanitize_path(payload[key])
    return payload


def sanitize_bazarr_movie(row: dict) -> dict:
    payload = json.loads(json.dumps(row))
    for key in ("path", "sceneName"):
        if payload.get(key):
            payload[key] = str(payload[key]).replace("\\", "/")
    return payload


def write_snapshot(path: Path, payload: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
