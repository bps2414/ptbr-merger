import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import src.bazarr_client as bazarr_client
import src.qbit_client as qbit_client
import src.radarr_client as radarr_client
from tests.support.api_snapshots import sanitize_qbit_torrent


SNAPSHOT_DIR = Path(__file__).resolve().parent / "test_data" / "api_snapshots"


def _load_snapshot(name: str) -> dict | list:
    return json.loads((SNAPSHOT_DIR / name).read_text(encoding="utf-8"))


def test_api_snapshot_manifest_matches_files():
    manifest = _load_snapshot("manifest.json")
    declared = set(manifest["snapshots"])
    actual = {path.name for path in SNAPSHOT_DIR.glob("*.json") if path.name != "capture_report.json"}

    assert declared <= actual


def test_radarr_release_snapshot_compatibility_uses_real_fields():
    release_snapshot = _load_snapshot("radarr_release_sample.json")
    assert isinstance(release_snapshot, list) and release_snapshot

    sample = release_snapshot[0]

    assert radarr_client._seeders_for_release(sample) == sample["seeders"]
    assert radarr_client._peers_for_release(sample) == sample["leechers"]
    assert radarr_client._protocol_for_release(sample) == sample["protocol"]
    assert sample.get("infoHash")


@patch("src.radarr_client.get_movie_by_tmdbid")
@patch("src.radarr_client._request")
def test_find_best_ptbr_release_preserves_infohash_from_radarr_snapshot(mock_request, mock_get_movie):
    movie_snapshot = _load_snapshot("radarr_movie_sample.json")
    release_snapshot = _load_snapshot("radarr_release_sample.json")

    movie = movie_snapshot[0] if isinstance(movie_snapshot, list) else movie_snapshot
    mock_get_movie.return_value = movie
    mock_request.return_value = release_snapshot

    candidates = radarr_client.find_best_ptbr_release(str(movie["tmdbId"]))

    assert candidates
    assert any(candidate.get("infohash") for candidate in candidates)


def test_qbit_snapshot_compatibility_supports_list_and_debug_views():
    torrent_snapshot = _load_snapshot("qbit_torrents_info_sample.json")
    assert isinstance(torrent_snapshot, list) and torrent_snapshot

    ptbr_torrent = next(item for item in torrent_snapshot if item.get("category") == "ptbrmerger")
    result = qbit_client._torrent_to_result(ptbr_torrent)

    assert result.success is True
    assert result.torrent_hash == ptbr_torrent["hash"]
    assert result.progress == pytest.approx(float(ptbr_torrent["progress"]) * 100, abs=0.01)


def test_qbit_snapshot_sanitizer_scrubs_windows_data_paths():
    sanitized = sanitize_qbit_torrent(
        {
            "hash": "abc",
            "save_path": r"D:\data\torrents\movies",
            "content_path": r"D:\data\temp\ptbrmerger\Movie",
        }
    )

    assert sanitized["save_path"].replace("/", "\\").startswith("D:\\media\\")
    assert sanitized["content_path"].replace("/", "\\").startswith("D:\\media\\")


@patch("src.bazarr_client.requests.get")
def test_bazarr_lookup_accepts_dict_data_payload(mock_get):
    payload = _load_snapshot("bazarr_movies_sample.json")
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = payload
    mock_get.return_value = response

    with patch.object(bazarr_client.config.bazarr, "url", "http://localhost:6767"), patch.object(
        bazarr_client.config.bazarr, "api_key", "dummy-key"
    ):
        result = bazarr_client.lookup_ptbr_subtitles("1218925", title="Chainsaw Man - The Movie: Reze Arc", year="2025")

    assert result["configured"] is True
    assert result["available"] is True
    assert result["subtitle_count"] >= 1


@patch("src.bazarr_client.requests.get")
def test_bazarr_lookup_does_not_treat_missing_subtitles_as_available(mock_get):
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "data": [
            {
                "title": "Chainsaw Man - The Movie: Reze Arc",
                "tmdbId": 1218925,
                "missing_subtitles": ["pt-BR"],
            }
        ]
    }
    mock_get.return_value = response

    with patch.object(bazarr_client.config.bazarr, "url", "http://localhost:6767"), patch.object(
        bazarr_client.config.bazarr, "api_key", "dummy-key"
    ):
        result = bazarr_client.lookup_ptbr_subtitles("1218925", title="Chainsaw Man - The Movie: Reze Arc", year="2025")

    assert result["configured"] is True
    assert result["available"] is False
    assert result["reason"] == "subtitle-not-found"
    assert result["subtitle_count"] == 0
