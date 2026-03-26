import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import src.notifier as notifier


def _response(payload=None):
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = payload or {}
    return response


@patch("src.notifier.requests.post")
def test_send_progress_update_creates_message_and_returns_id(mock_post):
    mock_post.return_value = _response({"id": "discord-message-1"})

    message_id = notifier.send_progress_update(
        phase="search",
        context={"title": "The Housemaid", "year": "2025", "candidate_index": 1},
    )

    assert message_id == "discord-message-1"
    _, kwargs = mock_post.call_args
    assert kwargs["params"] == {"wait": "true"}


@patch("src.notifier.requests.patch")
def test_send_progress_update_edits_existing_message(mock_patch):
    mock_patch.return_value = _response({"id": "discord-message-1"})

    message_id = notifier.send_progress_update(
        phase="mux",
        context={"title": "The Housemaid", "year": "2025"},
        message_id="discord-message-1",
    )

    assert message_id == "discord-message-1"
    assert mock_patch.call_count == 1


@patch("src.notifier.requests.post", side_effect=RuntimeError("blocked"))
def test_send_progress_update_fails_softly(mock_post):
    message_id = notifier.send_progress_update(
        phase="search",
        context={"title": "The Housemaid", "year": "2025"},
    )

    assert message_id is None
    assert mock_post.called


def test_build_embed_payload_includes_cover_progress_and_eta():
    payload = notifier._build_embed_payload(
        "PROGRESS",
        {
            "title": "The Housemaid",
            "year": "2025",
            "tmdbId": "1368166",
            "poster_url": "https://image.tmdb.org/t/p/original/poster.jpg",
            "release_title": "A.Empregada.2025.1080p.WEB-DL.DUAL.5.1",
            "indexer": "CatÃ¡logo Betor",
            "candidate_index": 1,
            "score": 47025,
            "process_runtime": 92.4,
            "eta_seconds": 180,
            "qbit_state": "downloading",
            "num_seeds": 4,
            "num_leechs": 2,
            "diff": 0.0,
            "offset_estimate": 0.0,
        },
        phase="mux",
    )

    embed = payload["embeds"][0]
    field_names = [field["name"] for field in embed["fields"]]

    assert embed["thumbnail"]["url"] == "https://image.tmdb.org/t/p/original/poster.jpg"
    assert "andamento" in embed["author"]["name"]
    assert embed["title"].startswith("The Housemaid")
    assert "78%" in next(field["value"] for field in embed["fields"] if field["name"] == "Progresso")
    assert "Progresso" in field_names
    assert "ETA" in field_names
    assert "Fase" in field_names
    assert "Release" in field_names
    assert "Estado qBit" in field_names
    assert "Seeds" in field_names
    assert "Peers" in field_names
    assert any("Diagn" in field for field in field_names)


def test_build_message_progress_is_human_readable():
    message = notifier._build_message(
        "PROGRESS",
        {"title": "Alien: Romulus", "year": "2024"},
    )

    assert message == "PROGRESS: Processando Alien: Romulus (2024)."


def test_build_message_not_found_includes_bazarr_context_when_available():
    message = notifier._build_message(
        "NOT_FOUND",
        {"title": "Sonic the Hedgehog 3", "year": "2024", "bazarr_status": "subtitle-found"},
    )

    assert "Bazarr: subtitle-found." in message


def test_build_embed_payload_includes_retry_context():
    payload = notifier._build_embed_payload(
        "NO_AVAILABLE_SEEDS",
        {
            "title": "Sonic the Hedgehog 3",
            "year": "2024",
            "tmdbId": "939243",
            "retry_reason": "NO_AVAILABLE_SEEDS",
            "retry_scheduled_at": "2026-03-25T18:00:00+00:00",
            "process_runtime": 12,
        },
        phase="search",
    )

    embed = payload["embeds"][0]
    field_names = [field["name"] for field in embed["fields"]]

    assert "Retry" in field_names
    assert any("tentativa" in field for field in field_names)


def test_build_message_manual_recovery_failed_includes_strategy():
    message = notifier._build_message(
        "MANUAL_RECOVERY_FAILED",
        {
            "title": "Sonic the Hedgehog 3",
            "year": "2024",
            "recovery_strategy": "edge-trim",
            "validation_reason": "RECOVERY_POSTCHECK_FAILED",
        },
    )

    assert "MANUAL_RECOVERY_FAILED" in message
    assert "edge-trim" in message


def test_build_embed_payload_includes_manual_recovery_fields():
    payload = notifier._build_embed_payload(
        "MANUAL_RECOVERY_SUCCESS",
        {
            "title": "Alien: Romulus",
            "year": "2024",
            "tmdbId": "945961",
            "manual_request_id": "manual-945961-20260326T120000Z",
            "manual_source_path": r"D:\downloads\Alien.1080p\movie.mkv",
            "manual_force_offset_seconds": -8.4,
            "recovery_strategy": "offset",
        },
        phase="finalize",
    )

    embed = payload["embeds"][0]
    field_names = [field["name"] for field in embed["fields"]]

    assert "Manual request" in field_names
    assert "Manual source" in field_names
