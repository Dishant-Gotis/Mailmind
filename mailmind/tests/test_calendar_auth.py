"""Tests for calendar_auth.py."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from exceptions import CalendarAPIError


@pytest.fixture(autouse=True)
def reset_cache():
    import calendar_auth

    calendar_auth._service = None
    calendar_auth._credentials = None
    yield
    calendar_auth._service = None
    calendar_auth._credentials = None


def _set_paths(tmp_path: Path) -> tuple[Path, Path]:
    import calendar_auth

    creds_path = tmp_path / "credentials.json"
    token_path = tmp_path / "data" / "token.json"

    creds_path.write_text("{}", encoding="utf-8")
    calendar_auth.config.google_calendar_credentials_path = str(creds_path)
    calendar_auth.config.google_calendar_token_path = str(token_path)

    return creds_path, token_path


def test_get_calendar_service_returns_cached_service(tmp_path):
    import calendar_auth

    _set_paths(tmp_path)

    creds = SimpleNamespace(valid=True)
    service = object()

    with patch("calendar_auth._load_or_refresh_credentials", return_value=creds) as mock_load, patch(
        "calendar_auth.build", return_value=service
    ) as mock_build:
        first = calendar_auth.get_calendar_service()
        second = calendar_auth.get_calendar_service()

    assert first is service
    assert second is service
    assert mock_load.call_count == 1
    assert mock_build.call_count == 1


def test_load_or_refresh_credentials_refreshes_expired_token(tmp_path):
    import calendar_auth

    _set_paths(tmp_path)
    calendar_auth.config.calendar_token_path.parent.mkdir(parents=True, exist_ok=True)
    calendar_auth.config.calendar_token_path.write_text("{}", encoding="utf-8")

    creds = MagicMock()
    creds.valid = False
    creds.expired = True
    creds.refresh_token = "refresh-token"

    def _refresh(_request):
        creds.valid = True

    creds.refresh.side_effect = _refresh

    with patch("calendar_auth.Credentials.from_authorized_user_file", return_value=creds) as mock_load, patch(
        "calendar_auth._save_token"
    ) as mock_save:
        result = calendar_auth._load_or_refresh_credentials()

    assert result is creds
    mock_load.assert_called_once()
    creds.refresh.assert_called_once()
    mock_save.assert_called_once()


def test_load_or_refresh_credentials_runs_oauth_when_token_missing(tmp_path):
    import calendar_auth

    _set_paths(tmp_path)

    creds = MagicMock()
    creds.valid = True

    flow = MagicMock()
    flow.run_local_server.return_value = creds

    with patch("calendar_auth.InstalledAppFlow.from_client_secrets_file", return_value=flow) as mock_flow, patch(
        "calendar_auth._save_token"
    ) as mock_save:
        result = calendar_auth._load_or_refresh_credentials()

    assert result is creds
    mock_flow.assert_called_once()
    flow.run_local_server.assert_called_once_with(port=0)
    mock_save.assert_called_once()


def test_load_or_refresh_credentials_raises_when_credentials_file_missing(tmp_path):
    import calendar_auth

    missing_creds = tmp_path / "missing" / "credentials.json"
    token_path = tmp_path / "data" / "token.json"
    calendar_auth.config.google_calendar_credentials_path = str(missing_creds)
    calendar_auth.config.google_calendar_token_path = str(token_path)

    with pytest.raises(CalendarAPIError) as exc_info:
        calendar_auth._load_or_refresh_credentials()

    assert "credentials.json" in str(exc_info.value)


def test_save_token_creates_parent_directory(tmp_path):
    import calendar_auth

    token_path = tmp_path / "nested" / "token.json"
    creds = MagicMock()
    creds.to_json.return_value = '{"ok": true}'

    calendar_auth._save_token(creds, token_path)

    assert token_path.exists()
    assert token_path.read_text(encoding="utf-8") == '{"ok": true}'
