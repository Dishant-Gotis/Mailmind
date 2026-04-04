"""
Google Calendar OAuth helpers for MailMind.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from config import config
from exceptions import CalendarAPIError
from logger import get_logger

logger = get_logger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]

_service: Any | None = None
_credentials: Credentials | None = None


def get_calendar_service() -> Any:
    """
    Return an authenticated and cached Google Calendar v3 service.
    """
    global _service, _credentials

    if _service is not None and _credentials is not None and _credentials.valid:
        return _service

    creds = _load_or_refresh_credentials()

    try:
        _service = build("calendar", "v3", credentials=creds)
        _credentials = creds
        logger.info("Google Calendar service initialised.")
        return _service
    except Exception as exc:
        raise CalendarAPIError(f"Failed to build Calendar service: {exc}") from exc


def _load_or_refresh_credentials() -> Credentials:
    """
    Load credentials from token storage, refresh when possible, or run OAuth flow.
    """
    token_path = config.calendar_token_path
    creds_path = config.calendar_credentials_path

    creds: Credentials | None = None

    if token_path.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        except Exception as exc:
            logger.warning("Failed to load token file %s: %s", token_path, exc)
            creds = None

    if creds and not creds.valid:
        if creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                _save_token(creds, token_path)
                logger.info("Google Calendar token refreshed.")
                return creds
            except Exception as exc:
                logger.warning("Token refresh failed: %s. Falling back to OAuth flow.", exc)
                creds = None

    if not creds:
        if not creds_path.exists():
            raise CalendarAPIError(
                "credentials.json not found at "
                f"'{creds_path}'. Download OAuth credentials from Google Cloud Console."
            )
        try:
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
            creds = flow.run_local_server(port=0)
            _save_token(creds, token_path)
            logger.info("Google Calendar OAuth flow completed.")
        except Exception as exc:
            raise CalendarAPIError(f"Google Calendar OAuth flow failed: {exc}") from exc

    if not creds or not creds.valid:
        raise CalendarAPIError("Unable to obtain valid Google Calendar credentials.")

    return creds


def _save_token(creds: Credentials, token_path: Path) -> None:
    """
    Persist OAuth credentials to token storage.
    """
    try:
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json(), encoding="utf-8")
    except Exception as exc:
        raise CalendarAPIError(f"Failed to save token file '{token_path}': {exc}") from exc
