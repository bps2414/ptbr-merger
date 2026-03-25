import os
import sys
from unittest.mock import MagicMock, patch

import pytest
import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import src.radarr_client as radarr_client


def _http_error(status_code: int) -> requests.exceptions.HTTPError:
    response = MagicMock()
    response.status_code = status_code
    response.text = f"HTTP {status_code}"
    return requests.exceptions.HTTPError(response=response)


@patch("src.radarr_client.time.sleep", return_value=None)
@patch("src.radarr_client.requests.request")
def test_request_retries_on_timeout(mock_request, _mock_sleep):
    success_response = MagicMock()
    success_response.status_code = 200
    success_response.text = "[]"
    success_response.json.return_value = []
    success_response.raise_for_status.return_value = None

    mock_request.side_effect = [
        requests.exceptions.Timeout("slow"),
        success_response,
    ]

    result = radarr_client._request("GET", "/api/v3/movie")

    assert result == []
    assert mock_request.call_count == 2


@patch("src.radarr_client.time.sleep", return_value=None)
@patch("src.radarr_client.requests.request")
def test_request_does_not_retry_on_404(mock_request, _mock_sleep):
    response = MagicMock()
    response.raise_for_status.side_effect = _http_error(404)
    response.text = "missing"
    mock_request.return_value = response

    with pytest.raises(requests.exceptions.HTTPError):
        radarr_client._request("GET", "/api/v3/movie")

    assert mock_request.call_count == 1


@patch("src.radarr_client._request")
def test_apply_success_tag_uses_movie_editor_add_mode(mock_request):
    mock_request.side_effect = [
        [{"label": "other", "id": 2}],
        {"id": 5},
        MagicMock(),
    ]

    radarr_client.apply_success_tag(movie_id=42)

    assert mock_request.call_args_list[1].args == ("POST", "/api/v3/tag")
    assert mock_request.call_args_list[2].args == ("PUT", "/api/v3/movie/editor")
    assert mock_request.call_args_list[2].kwargs["json"] == {
        "movieIds": [42],
        "tags": [5],
        "applyTags": "add",
    }


@patch("src.radarr_client.get_movie_by_tmdbid")
@patch("src.radarr_client._request")
def test_find_best_ptbr_release_skips_candidates_with_zero_seeders(mock_request, mock_get_movie):
    mock_get_movie.return_value = {
        "id": 49,
        "movieFile": {"path": r"D:\media\movie4k.mkv"},
    }
    mock_request.return_value = [
        {
            "title": "Movie.2026.1080p.WEBRip.Dublado.mkv",
            "customFormatScore": 15000,
            "quality": {"quality": {"name": "WEBRip-1080p"}},
            "downloadUrl": "https://tracker.example/zero",
            "indexer": "Catálogo Betor",
            "seeders": 0,
            "peers": 9,
            "protocol": "torrent",
            "size": 1,
        },
        {
            "title": "Movie.2026.1080p.WEBRip.DUAL.mkv",
            "customFormatScore": 15000,
            "quality": {"quality": {"name": "WEBRip-1080p"}},
            "downloadUrl": "https://tracker.example/good",
            "indexer": "Catálogo Betor",
            "seeders": 5,
            "peers": 10,
            "protocol": "torrent",
            "size": 2,
        },
    ]

    candidates = radarr_client.find_best_ptbr_release("49")

    assert [candidate["title"] for candidate in candidates] == ["Movie.2026.1080p.WEBRip.DUAL.mkv"]
    assert candidates[0]["seeders"] == 5
    assert candidates[0]["peers"] == 10
    assert candidates[0]["protocol"] == "torrent"


@patch("src.radarr_client.get_movie_by_tmdbid")
@patch("src.radarr_client._request")
def test_find_best_ptbr_release_returns_empty_when_all_candidates_have_zero_seeders(mock_request, mock_get_movie):
    mock_get_movie.return_value = {
        "id": 49,
        "movieFile": {"path": r"D:\media\movie4k.mkv"},
    }
    mock_request.return_value = [
        {
            "title": "Movie.2026.1080p.WEBRip.Dublado.mkv",
            "customFormatScore": 15000,
            "quality": {"quality": {"name": "WEBRip-1080p"}},
            "downloadUrl": "https://tracker.example/zero",
            "indexer": "Catálogo Betor",
            "seeders": 0,
            "peers": 9,
            "protocol": "torrent",
            "size": 1,
        }
    ]

    candidates = radarr_client.find_best_ptbr_release("49")

    assert candidates == []


@patch("src.radarr_client.get_movie_by_tmdbid")
@patch("src.radarr_client._request")
def test_find_best_ptbr_release_prefers_dual_ptbr_over_plain_dublado(mock_request, mock_get_movie):
    mock_get_movie.return_value = {
        "id": 49,
        "movieFile": {"path": r"D:\media\movie4k.mkv"},
    }
    mock_request.return_value = [
        {
            "title": "Movie.2026.1080p.WEBRip.Dublado.mkv",
            "customFormatScore": 15000,
            "quality": {"quality": {"name": "WEBRip-1080p"}},
            "downloadUrl": "https://tracker.example/dublado",
            "indexer": "Catálogo Betor",
            "seeders": 5,
            "peers": 10,
            "protocol": "torrent",
            "size": 1,
        },
        {
            "title": "Movie.2026.1080p.WEB-DL.DUAL.PT-BR.mkv",
            "customFormatScore": 15000,
            "quality": {"quality": {"name": "WEBDL-1080p"}},
            "downloadUrl": "https://tracker.example/dual",
            "indexer": "Catálogo Betor",
            "seeders": 4,
            "peers": 8,
            "protocol": "torrent",
            "size": 2,
        },
    ]

    candidates = radarr_client.find_best_ptbr_release("49")

    assert candidates[0]["title"] == "Movie.2026.1080p.WEB-DL.DUAL.PT-BR.mkv"
    assert "dublado" in candidates[1]["justificativa"].lower()


@patch("src.radarr_client.get_movie_by_tmdbid")
@patch("src.radarr_client._request")
def test_find_best_ptbr_release_prefers_more_seeders_when_scores_tie(mock_request, mock_get_movie):
    mock_get_movie.return_value = {
        "id": 49,
        "movieFile": {"path": r"D:\media\movie4k.mkv"},
    }
    mock_request.return_value = [
        {
            "title": "Movie.2026.1080p.WEB-DL.DUAL.5.1 [portuguese,english]",
            "customFormatScore": 15000,
            "quality": {"quality": {"name": "WEBDL-1080p"}},
            "downloadUrl": "https://tracker.example/low",
            "indexer": "Catálogo Betor",
            "seeders": 1,
            "peers": 3,
            "protocol": "torrent",
            "size": 2,
        },
        {
            "title": "Movie.2026.1080p.WEB-DL.DUAL.5.1 [portuguese,english] FULLHD",
            "customFormatScore": 15000,
            "quality": {"quality": {"name": "WEBDL-1080p"}},
            "downloadUrl": "https://tracker.example/high",
            "indexer": "Catálogo Betor",
            "seeders": 9,
            "peers": 12,
            "protocol": "torrent",
            "size": 2,
        },
    ]

    candidates = radarr_client.find_best_ptbr_release("49")

    assert candidates[0]["seeders"] == 9
    assert candidates[0]["peers"] == 12


@patch("src.radarr_client.group_history_manager.score_candidate")
@patch("src.radarr_client.get_movie_by_tmdbid")
@patch("src.radarr_client._request")
def test_find_best_ptbr_release_uses_history_bonus_to_promote_known_good_combo(mock_request, mock_get_movie, mock_score_candidate):
    mock_get_movie.return_value = {
        "id": 49,
        "movieFile": {"path": r"D:\media\Movie.2026.2160p.AMZN.WEB-DL.mkv"},
    }
    mock_request.return_value = [
        {
            "title": "Movie.2026.1080p.WEBRip.Dublado.mkv",
            "customFormatScore": 15000,
            "quality": {"quality": {"name": "WEBRip-1080p"}},
            "downloadUrl": "https://tracker.example/dublado",
            "indexer": "Catálogo Betor",
            "seeders": 8,
            "peers": 10,
            "protocol": "torrent",
            "size": 1,
        },
        {
            "title": "Movie.2026.1080p.WEB-DL.DUAL.PT-BR-BYNDR",
            "customFormatScore": 15000,
            "quality": {"quality": {"name": "WEBDL-1080p"}},
            "downloadUrl": "https://tracker.example/dual",
            "indexer": "Catálogo Betor",
            "seeders": 2,
            "peers": 8,
            "protocol": "torrent",
            "size": 2,
        },
    ]
    mock_score_candidate.side_effect = [(0, "history:none"), (12, "combo-success:+12")]

    candidates = radarr_client.find_best_ptbr_release("49")

    assert candidates[0]["title"] == "Movie.2026.1080p.WEB-DL.DUAL.PT-BR-BYNDR"
    assert candidates[0]["history_bonus"] == 12


@patch("src.radarr_client.get_movie_by_tmdbid")
@patch("src.radarr_client._request")
def test_find_best_ptbr_release_skips_generic_non_ptbr_remux_even_with_high_cf_score(mock_request, mock_get_movie):
    mock_get_movie.return_value = {
        "id": 56,
        "movieFile": {"path": r"D:\media\the-crow-4k.mkv"},
    }
    mock_request.return_value = [
        {
            "title": "The.Crow.1994.4K.Remastered.1080p.BluRay.Remux.DTS-HD.5.1",
            "customFormatScore": 10300,
            "quality": {"quality": {"name": "Remux-1080p"}},
            "downloadUrl": "https://tracker.example/remux",
            "indexer": "Torrentio (Prowlarr)",
            "seeders": 20,
            "peers": 30,
            "protocol": "torrent",
            "size": 28000000000,
        }
    ]

    candidates = radarr_client.find_best_ptbr_release("56")

    assert candidates == []


@patch("src.radarr_client.get_movie_by_tmdbid")
@patch("src.radarr_client._request")
def test_find_best_ptbr_release_accepts_dual_on_br_indexer_without_explicit_ptbr_token(mock_request, mock_get_movie):
    mock_get_movie.return_value = {
        "id": 49,
        "movieFile": {"path": r"D:\media\movie4k.mkv"},
    }
    mock_request.return_value = [
        {
            "title": "Movie.2026.1080p.WEBRip.DUAL.mkv",
            "customFormatScore": 15000,
            "quality": {"quality": {"name": "WEBRip-1080p"}},
            "downloadUrl": "https://tracker.example/dual",
            "indexer": "Catálogo Betor",
            "seeders": 5,
            "peers": 10,
            "protocol": "torrent",
            "size": 1,
        }
    ]

    candidates = radarr_client.find_best_ptbr_release("49")

    assert len(candidates) == 1
    assert candidates[0]["title"] == "Movie.2026.1080p.WEBRip.DUAL.mkv"


@patch("src.radarr_client.group_history_manager.score_candidate", return_value=(0, "history:none"))
@patch("src.radarr_client.get_movie_by_tmdbid")
@patch("src.radarr_client._request")
def test_find_best_ptbr_release_adds_exploratory_dual_candidates_after_strict_bank(
    mock_request,
    mock_get_movie,
    _mock_score_candidate,
):
    mock_get_movie.return_value = {
        "id": 51,
        "movieFile": {"path": r"D:\media\Sonic.3.2160p.WEB-DL.mkv"},
    }
    mock_request.return_value = [
        {
            "title": "Movie.2026.1080p.WEB-DL.DUAL.PT-BR.mkv",
            "customFormatScore": 15000,
            "quality": {"quality": {"name": "WEBDL-1080p"}},
            "downloadUrl": "https://tracker.example/strict",
            "indexer": "Catálogo Betor",
            "seeders": 5,
            "peers": 10,
            "protocol": "torrent",
            "size": 2,
        },
        {
            "title": "Movie.2026.1080p.WEB-DL.Dual.Audio.Multi-Subs",
            "customFormatScore": 14900,
            "quality": {"quality": {"name": "WEBDL-1080p"}},
            "downloadUrl": "https://tracker.example/exploratory",
            "indexer": "Torrentio (Prowlarr)",
            "seeders": 8,
            "peers": 10,
            "protocol": "torrent",
            "size": 2,
        },
    ]

    candidates = radarr_client.find_best_ptbr_release("51")

    assert len(candidates) == 2
    assert candidates[0]["evidence_level"] == "strict"
    assert candidates[1]["evidence_level"] == "exploratory"
    assert "exploratory-evidence:dual-exploratory" in candidates[1]["justificativa"]


@patch("src.radarr_client.group_history_manager.score_candidate", return_value=(0, "history:none"))
@patch("src.radarr_client.get_movie_by_tmdbid")
@patch("src.radarr_client._request")
def test_find_best_ptbr_release_skips_exploratory_dual_with_explicit_foreign_audio_markers(
    mock_request,
    mock_get_movie,
    _mock_score_candidate,
):
    mock_get_movie.return_value = {
        "id": 51,
        "movieFile": {"path": r"D:\media\Sonic.3.2160p.WEB-DL.mkv"},
    }
    mock_request.return_value = [
        {
            "title": "Sonic.3.La.Película.2024.1080p-Dual-Lat",
            "customFormatScore": 18500,
            "quality": {"quality": {"name": "WEBDL-1080p"}},
            "downloadUrl": "https://tracker.example/lat",
            "indexer": "Torrentio (Prowlarr)",
            "seeders": 10,
            "peers": 10,
            "protocol": "torrent",
            "size": 2,
        },
        {
            "title": "Sonic.3.Il.Film.2024.iTA-ENG.WEBDL.1080p.x264-CYBER.mkv",
            "customFormatScore": 18000,
            "quality": {"quality": {"name": "WEBDL-1080p"}},
            "downloadUrl": "https://tracker.example/ita",
            "indexer": "Torrentio (Prowlarr)",
            "seeders": 7,
            "peers": 7,
            "protocol": "torrent",
            "size": 2,
        },
    ]

    candidates = radarr_client.find_best_ptbr_release("51")

    assert candidates == []


@patch("src.radarr_client.group_history_manager.score_candidate", return_value=(-40, "combo-cut:-36, group-bad:-4"))
@patch("src.radarr_client.get_movie_by_tmdbid")
@patch("src.radarr_client._request")
def test_find_best_ptbr_release_skips_precheck_bad_candidates(
    mock_request,
    mock_get_movie,
    _mock_score_candidate,
):
    mock_get_movie.return_value = {
        "id": 51,
        "movieFile": {"path": r"D:\media\Sonic.3.2160p.WEB-DL.mkv"},
        "runtime": 110,
    }
    mock_request.return_value = [
        {
            "title": "Movie.2026.1080p.WEB-DL.DUAL.PT-BR.mkv",
            "customFormatScore": 15000,
            "quality": {"quality": {"name": "WEBDL-1080p"}},
            "downloadUrl": "https://tracker.example/strict",
            "indexer": "Catálogo Betor",
            "seeders": 5,
            "peers": 10,
            "protocol": "torrent",
            "size": 2,
        }
    ]

    candidates = radarr_client.find_best_ptbr_release("51")

    assert candidates == []
    summary = radarr_client.get_last_release_search_summary("51")
    assert summary["reason"] == "NO_MATCHES"
    assert summary["skipped_precheck"][0]["title"] == "Movie.2026.1080p.WEB-DL.DUAL.PT-BR.mkv"


@patch("src.radarr_client.get_movie_by_tmdbid")
@patch("src.radarr_client._request")
def test_find_best_ptbr_release_records_low_score_and_missing_url_rejections(mock_request, mock_get_movie):
    mock_get_movie.return_value = {
        "id": 49,
        "movieFile": {"path": r"D:\media\movie4k.mkv"},
    }
    mock_request.return_value = [
        {
            "title": "Movie.2026.1080p.WEBRip.Dublado.mkv",
            "customFormatScore": 9999,
            "quality": {"quality": {"name": "WEBRip-1080p"}},
            "downloadUrl": "https://tracker.example/low",
            "indexer": "Catálogo Betor",
            "seeders": 3,
            "size": 1,
        },
        {
            "title": "Movie.2026.1080p.WEB-DL.DUAL.PT-BR.mkv",
            "customFormatScore": 15000,
            "quality": {"quality": {"name": "WEBDL-1080p"}},
            "downloadUrl": "",
            "magnetUrl": "",
            "indexer": "Catálogo Betor",
            "seeders": 5,
            "size": 2,
        },
    ]

    candidates = radarr_client.find_best_ptbr_release("49")

    assert candidates == []
    summary = radarr_client.get_last_release_search_summary("49")
    assert len(summary["skipped_low_score_or_url"]) == 2
    assert summary["skipped_low_score_or_url"][0]["missing_url"] is False
    assert summary["skipped_low_score_or_url"][1]["missing_url"] is True
