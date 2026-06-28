from unittest.mock import MagicMock, patch

from requests.exceptions import Timeout

from app import monitor


def _target():
    return {
        "id": 1,
        "name": "svc",
        "url": "https://example.com",
        "method": "GET",
        "headers": "{}",
        "body": None,
        "expected_status": 200,
        "timeout": 5,
    }


@patch.object(monitor._session, "request")
def test_probe_success(mock_request):
    response = MagicMock()
    response.status_code = 200
    response.content = b"hello"
    response.elapsed.total_seconds.return_value = 0.123
    mock_request.return_value = response

    result = monitor.probe(_target())
    assert result.success is True
    assert result.status_code == 200
    assert result.response_time_ms == 123.0
    assert result.response_size == 5
    assert result.error is None


@patch.object(monitor._session, "request")
def test_probe_unexpected_status(mock_request):
    response = MagicMock()
    response.status_code = 503
    response.content = b""
    response.elapsed.total_seconds.return_value = 0.05
    mock_request.return_value = response

    result = monitor.probe(_target())
    assert result.success is False
    assert "unexpected status 503" in result.error


@patch.object(monitor._session, "request", side_effect=Timeout())
def test_probe_timeout(mock_request):
    result = monitor.probe(_target())
    assert result.success is False
    assert result.status_code is None
    assert "timeout" in result.error
