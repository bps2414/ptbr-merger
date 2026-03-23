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
