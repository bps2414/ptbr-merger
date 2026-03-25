import argparse
import json
import sys
from pathlib import Path

import requests
import yaml

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from tests.support.api_snapshots import (  # noqa: E402
    sanitize_bazarr_movie,
    sanitize_qbit_torrent,
    sanitize_radarr_movie,
    sanitize_radarr_release,
    write_snapshot,
)
from src.radarr_client import (  # noqa: E402
    _has_exploratory_ptbr_evidence,
    _has_minimum_ptbr_evidence,
    _has_relaxed_ptbr_evidence,
)


def _load_config() -> dict:
    return yaml.safe_load((ROOT_DIR / "config.yml").read_text(encoding="utf-8"))


def _compact_radarr_movie(movie: dict) -> dict:
    return {
        "id": movie.get("id"),
        "title": movie.get("title"),
        "year": movie.get("year"),
        "tmdbId": movie.get("tmdbId"),
        "imdbId": movie.get("imdbId"),
        "runtime": movie.get("runtime"),
        "hasFile": movie.get("hasFile"),
        "path": movie.get("path"),
        "movieFile": movie.get("movieFile"),
        "images": movie.get("images"),
        "status": movie.get("status"),
    }


def _compact_radarr_release(release: dict) -> dict:
    return {
        "title": release.get("title"),
        "downloadUrl": release.get("downloadUrl"),
        "magnetUrl": release.get("magnetUrl"),
        "protocol": release.get("protocol"),
        "indexer": release.get("indexer"),
        "customFormatScore": release.get("customFormatScore"),
        "quality": release.get("quality"),
        "size": release.get("size"),
        "seeders": release.get("seeders"),
        "leechers": release.get("leechers"),
        "infoHash": release.get("infoHash"),
        "languages": release.get("languages"),
        "releaseGroup": release.get("releaseGroup"),
        "sceneSource": release.get("sceneSource"),
    }


def _select_radarr_release_rows(releases: list[dict]) -> list[dict]:
    prioritized = []
    for release in releases:
        title = str(release.get("title") or "").lower()
        quality_name = str((release.get("quality") or {}).get("quality", {}).get("name") or "")
        if "1080" not in quality_name:
            continue
        score = 0
        strict_ok, _ = _has_minimum_ptbr_evidence(release)
        soft_ok, _ = _has_relaxed_ptbr_evidence(release)
        exploratory_ok, _ = _has_exploratory_ptbr_evidence(release)
        if strict_ok:
            score += 100
        elif soft_ok:
            score += 70
        elif exploratory_ok:
            score += 40
        if any(token in title for token in ("portugu", "pt-br", "dublado", "o.filme")):
            score += 10
        if "dual" in title:
            score += 3
        if score:
            prioritized.append((score, release))
    if prioritized:
        prioritized.sort(key=lambda item: item[0], reverse=True)
        return [release for _, release in prioritized[:5]]
    return releases[:5]


def _movie_release_priority(releases: list[dict]) -> tuple[int, int]:
    strict_hits = 0
    soft_hits = 0
    exploratory_hits = 0
    for release in releases:
        quality_name = str((release.get("quality") or {}).get("quality", {}).get("name") or "")
        if "1080" not in quality_name:
            continue
        if _has_minimum_ptbr_evidence(release)[0]:
            strict_hits += 1
        elif _has_relaxed_ptbr_evidence(release)[0]:
            soft_hits += 1
        elif _has_exploratory_ptbr_evidence(release)[0]:
            exploratory_hits += 1
    return (strict_hits, soft_hits + exploratory_hits)


def _capture_radarr(cfg: dict, output_dir: Path, report: dict) -> None:
    headers = {"X-Api-Key": cfg["radarr"]["api_key"]}
    base_url = cfg["radarr"]["url"]
    movies = requests.get(base_url + "/api/v3/movie", headers=headers, timeout=20).json()
    movie = None
    releases = []
    best_priority = (-1, -1)
    for candidate in movies if isinstance(movies, list) else []:
        if not candidate.get("hasFile"):
            continue
        candidate_releases = requests.get(
            base_url + f"/api/v3/release?movieId={candidate['id']}",
            headers=headers,
            timeout=60,
        ).json()
        if not isinstance(candidate_releases, list):
            continue
        priority = _movie_release_priority(candidate_releases)
        if priority > best_priority:
            best_priority = priority
            movie = candidate
            releases = candidate_releases
        if priority[0] >= 2:
            break
    if not movie:
        report["radarr"] = {"status": "empty"}
        return
    release_rows = _select_radarr_release_rows(releases if isinstance(releases, list) else [])
    write_snapshot(output_dir / "radarr_movie_sample.json", [sanitize_radarr_movie(_compact_radarr_movie(movie))])
    write_snapshot(
        output_dir / "radarr_release_sample.json",
        [sanitize_radarr_release(_compact_radarr_release(item)) for item in release_rows],
    )
    report["radarr"] = {
        "status": "captured",
        "movie_id": movie["id"],
        "release_rows": len(release_rows),
        "selection_priority": {"strict": best_priority[0], "soft_or_exploratory": best_priority[1]},
    }


def _capture_qbit(cfg: dict, output_dir: Path, report: dict) -> None:
    base_url = cfg["qbittorrent"]["url"]
    session = requests.Session()
    response = session.post(
        base_url + "/api/v2/auth/login",
        data={"username": cfg["qbittorrent"]["username"], "password": cfg["qbittorrent"]["password"]},
        timeout=10,
    )
    response.raise_for_status()
    torrents = session.get(base_url + "/api/v2/torrents/info", params={"filter": "all"}, timeout=10).json()
    rows = torrents[:10] if isinstance(torrents, list) else []
    write_snapshot(output_dir / "qbit_torrents_info_sample.json", [sanitize_qbit_torrent(item) for item in rows])
    report["qbittorrent"] = {"status": "captured", "rows": len(rows)}


def _capture_bazarr(cfg: dict, output_dir: Path, report: dict) -> None:
    bazarr_cfg = cfg.get("bazarr") or {}
    base_url = str(bazarr_cfg.get("url") or "").strip()
    api_key = str(bazarr_cfg.get("api_key") or "").strip()
    if not base_url or not api_key:
        report["bazarr"] = {"status": "skipped", "reason": "missing-config"}
        return
    response = requests.get(base_url + "/api/movies", headers={"X-API-KEY": api_key}, timeout=20)
    response.raise_for_status()
    payload = response.json()
    rows = payload.get("data") if isinstance(payload, dict) else payload
    rows = rows[:10] if isinstance(rows, list) else []
    write_snapshot(output_dir / "bazarr_movies_sample.json", {"data": [sanitize_bazarr_movie(item) for item in rows]})
    report["bazarr"] = {"status": "captured", "rows": len(rows)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture sanitized API snapshots for Phase 3D.")
    parser.add_argument("--output-dir", default="tests/test_data/api_snapshots", help="Snapshot output directory.")
    args = parser.parse_args()

    cfg = _load_config()
    output_dir = (ROOT_DIR / args.output_dir).resolve()
    report = {}

    try:
        _capture_radarr(cfg, output_dir, report)
    except Exception as exc:
        report["radarr"] = {"status": "failed", "reason": str(exc)}

    try:
        _capture_qbit(cfg, output_dir, report)
    except Exception as exc:
        report["qbittorrent"] = {"status": "failed", "reason": str(exc)}

    try:
        _capture_bazarr(cfg, output_dir, report)
    except Exception as exc:
        report["bazarr"] = {"status": "failed", "reason": str(exc)}

    (output_dir / "capture_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
