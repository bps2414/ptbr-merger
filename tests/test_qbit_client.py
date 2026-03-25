import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import src.qbit_client as qbit_client


def _response(text: str, status_code: int = 200, json_data=None) -> MagicMock:
    response = MagicMock()
    response.text = text
    response.status_code = status_code
    response.raise_for_status.return_value = None
    response.is_redirect = status_code in {301, 302, 303, 307, 308}
    response.headers = {}
    response.json.return_value = json_data
    return response


@patch("src.qbit_client._extract_infohash_from_url", return_value=None)
@patch("src.qbit_client.time.sleep", return_value=None)
@patch("src.qbit_client._prioritize_ptbrmerger_downloads_with_session", return_value=True)
@patch("src.qbit_client.login")
def test_add_torrent_returns_failure_when_qbit_accepts_request_but_torrent_never_appears(
    mock_login,
    _mock_prioritize,
    _mock_sleep,
    _mock_infohash,
):
    session = MagicMock()
    session.post.return_value = _response("Fails.")
    session.get.return_value = _response("[]", json_data=[])
    mock_login.return_value = session

    result = qbit_client.add_torrent("https://tracker.example/torrent/123", "1368166")

    assert result.success is False


@patch("src.qbit_client._extract_infohash_from_url", return_value=None)
@patch("src.qbit_client.time.sleep", return_value=None)
@patch("src.qbit_client._prioritize_ptbrmerger_downloads_with_session", return_value=True)
@patch("src.qbit_client.login")
def test_add_torrent_returns_success_when_qbit_lists_torrent_after_add(
    mock_login,
    _mock_prioritize,
    _mock_sleep,
    _mock_infohash,
):
    session = MagicMock()
    session.post.return_value = _response("Ok.")
    before_response = _response("[]", json_data=[])
    after_payload = [
        {
            "hash": "abc123",
            "state": "downloading",
            "name": "A.Empregada.2025.1080p.WEB-DL.DUAL.5.1",
            "content_path": r"D:\Filmes\A.Empregada",
            "save_path": r"D:\Filmes",
            "progress": 0.15,
        }
    ]
    after_response = _response("payload", json_data=after_payload)
    refreshed_response = _response("payload", json_data=after_payload)
    session.get.side_effect = [before_response, after_response, refreshed_response]
    mock_login.return_value = session

    result = qbit_client.add_torrent("https://tracker.example/torrent/123", "1368166")

    assert result.success is True
    assert result.existing is False
    assert result.torrent_hash == "abc123"


@patch("src.qbit_client._extract_infohash_from_url", return_value="ff9b9024d88c50f30b03f76e16172a180a450daa")
@patch("src.qbit_client._prioritize_ptbrmerger_downloads_with_session", return_value=True)
@patch("src.qbit_client.login")
def test_add_torrent_reuses_existing_duplicate_and_applies_metadata(mock_login, _mock_prioritize, _mock_infohash):
    session = MagicMock()
    duplicate_payload = [
        {
            "hash": "ff9b9024d88c50f30b03f76e16172a180a450daa",
            "state": "uploading",
            "name": "A.Empregada.2025.1080p.WEB-DL.DUAL.5.1",
            "content_path": r"D:\Filmes\A.Empregada.2025.1080p.WEB-DL.DUAL.5.1",
            "save_path": r"D:\Filmes",
            "progress": 1.0,
        }
    ]
    by_tag_response = _response("[]", json_data=[])
    by_hash_initial = _response("payload", json_data=duplicate_payload)
    by_hash_refreshed = _response("payload", json_data=duplicate_payload)
    session.get.side_effect = [by_tag_response, by_hash_initial, by_hash_refreshed]
    session.post.return_value = _response("")
    mock_login.return_value = session

    result = qbit_client.add_torrent("https://tracker.example/torrent/123", "1368166")

    assert result.success is True
    assert result.existing is True
    assert result.completed is True
    assert result.torrent_hash == "ff9b9024d88c50f30b03f76e16172a180a450daa"
    assert session.post.call_count == 2


@patch("src.qbit_client._extract_infohash_from_url")
@patch("src.qbit_client._prioritize_ptbrmerger_downloads_with_session", return_value=True)
@patch("src.qbit_client.login")
def test_add_torrent_prefers_known_infohash_over_url_resolution(mock_login, _mock_prioritize, mock_extract_infohash):
    session = MagicMock()
    duplicate_payload = [
        {
            "hash": "knownhash123",
            "state": "uploading",
            "name": "Chainsaw.Man.O.Filme.Arco.da.Reze.2025.1080p.WEB-DL.DUAL.5.1",
            "content_path": r"D:\Filmes\Chainsaw.Man.O.Filme.Arco.da.Reze.2025.1080p.WEB-DL.DUAL.5.1",
            "save_path": r"D:\Filmes",
            "progress": 1.0,
        }
    ]
    session.get.side_effect = [
        _response("[]", json_data=[]),
        _response("payload", json_data=duplicate_payload),
        _response("payload", json_data=duplicate_payload),
    ]
    session.post.return_value = _response("")
    mock_login.return_value = session

    result = qbit_client.add_torrent(
        "https://tracker.example/torrent/123",
        "1218925",
        known_infohash="knownhash123",
    )

    assert result.success is True
    assert result.existing is True
    assert result.torrent_hash == "knownhash123"
    mock_extract_infohash.assert_not_called()


@patch("src.qbit_client._extract_infohash_from_url", return_value="af4673c60613cb4e7b2e71319e883af04b990c26")
@patch("src.qbit_client.time.sleep", return_value=None)
@patch("src.qbit_client._prioritize_ptbrmerger_downloads_with_session", return_value=True)
@patch("src.qbit_client.login")
def test_add_torrent_prefers_new_hash_when_old_tagged_torrent_already_exists(
    mock_login,
    _mock_prioritize,
    _mock_sleep,
    _mock_infohash,
):
    session = MagicMock()
    session.post.return_value = _response("Ok.")

    old_tagged_payload = [
        {
            "hash": "ff9b9024d88c50f30b03f76e16172a180a450daa",
            "state": "stalledUP",
            "name": "A.Empregada.2025.1080p.WEB-DL.DUAL.5.1",
            "content_path": r"D:\Filmes\A.Empregada.2025.1080p.WEB-DL.DUAL.5.1",
            "save_path": r"D:\Filmes",
            "progress": 1.0,
        }
    ]
    mixed_payload = old_tagged_payload + [
        {
            "hash": "af4673c60613cb4e7b2e71319e883af04b990c26",
            "state": "downloading",
            "name": "A.Empregada.2025.WEB-DL.1080p.x264.DUAL.5.1-SF",
            "content_path": r"D:\data\temp\ptbrmerger\A.Empregada.2025.WEB-DL.1080p.x264.DUAL.5.1-SF",
            "save_path": r"D:\data\temp\ptbrmerger",
            "progress": 0.02,
        }
    ]

    session.get.side_effect = [
        _response("payload", json_data=old_tagged_payload),
        _response("payload", json_data=[]),
        _response("payload", json_data=mixed_payload),
        _response("payload", json_data=mixed_payload),
    ]
    mock_login.return_value = session

    result = qbit_client.add_torrent("https://tracker.example/torrent/456", "1368166")

    assert result.success is True
    assert result.existing is False
    assert result.torrent_hash == "af4673c60613cb4e7b2e71319e883af04b990c26"


@patch("src.qbit_client.login")
def test_prioritize_ptbrmerger_downloads_moves_ptbr_to_top_and_radarr_to_bottom(mock_login):
    session = MagicMock()
    session.get.return_value = _response(
        "payload",
        json_data=[
            {
                "hash": "pt1",
                "category": "ptbrmerger",
                "tags": "ptbrmerger-tmdbid-945961",
                "state": "downloading",
                "progress": 0.5,
            },
            {
                "hash": "rd1",
                "category": "radarr",
                "tags": "",
                "state": "downloading",
                "progress": 0.8,
            },
        ],
    )
    session.post.return_value = _response("")
    mock_login.return_value = session

    qbit_client.prioritize_ptbrmerger_downloads()

    post_urls = [call.args[0] for call in session.post.call_args_list]
    assert any(url.endswith("/api/v2/torrents/topPrio") for url in post_urls)
    assert any(url.endswith("/api/v2/torrents/bottomPrio") for url in post_urls)
