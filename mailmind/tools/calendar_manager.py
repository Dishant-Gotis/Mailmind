"""
Google Calendar tool functions for duplicate checks, creation, and invite dispatch.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from exceptions import CalendarAPIError
from logger import get_logger

logger = get_logger(__name__)


def _get_service():
    """
    Return authenticated Calendar service. Expected provider lands in Phase 8.
    """
    try:
        from calendar_auth import get_calendar_service
    except ImportError as exc:
        raise CalendarAPIError(
            "calendar_auth.py is not available yet. Implement calendar auth before using calendar tools."
        ) from exc

    try:
        return get_calendar_service()
    except Exception as exc:
        raise CalendarAPIError(f"Failed to create calendar service: {exc}") from exc


def _to_utc_aware(dt) -> datetime:
    from datetime import timezone
    if isinstance(dt, str):
        if dt.endswith("Z"):
            dt = dt.replace("Z", "+00:00")
        dt = datetime.fromisoformat(dt)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def check_duplicate(title: str, start_utc: str | datetime, participants: list[str]) -> dict[str, Any]:
    """
    Detect existing events near the start time that match title and participants.
    """
    try:
        service = _get_service()
        start_dt = _to_utc_aware(start_utc)
        time_min = (start_dt - timedelta(hours=1)).isoformat()
        time_max = (start_dt + timedelta(hours=1)).isoformat()

        events = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
            .get("items", [])
        )

        participants_lower = {email.lower() for email in participants}
        title_lower = title.lower()

        for event in events:
            summary = str(event.get("summary", "")).lower()
            if title_lower not in summary:
                continue

            attendee_emails = {
                str(attendee.get("email", "")).lower()
                for attendee in event.get("attendees", [])
                if attendee.get("email")
            }

            if attendee_emails & participants_lower:
                return {"duplicate": True, "event_id": event.get("id")}

        return {"duplicate": False, "event_id": None}
    except CalendarAPIError:
        raise
    except Exception as exc:
        raise CalendarAPIError(f"check_duplicate failed: {exc}") from exc


def create_event(
    title: str,
    start_utc: str,
    end_utc: str,
    participants: list[str],
    description: str = "",
) -> dict[str, Any]:
    """
    Create a Calendar event and return event metadata.
    """
    try:
        service = _get_service()
        attendees = [{"email": email} for email in participants]

        event_body = {
            "summary": title,
            "description": description,
            "start": {"dateTime": start_utc, "timeZone": "UTC"},
            "end": {"dateTime": end_utc, "timeZone": "UTC"},
            "attendees": attendees,
            "reminders": {
                "useDefault": False,
                "overrides": [
                    {"method": "email", "minutes": 24 * 60},
                    {"method": "popup", "minutes": 15},
                ],
            },
            "guestsCanModify": False,
            "guestsCanInviteOthers": False,
        }

        created = (
            service.events()
            .insert(calendarId="primary", body=event_body, sendUpdates="all")
            .execute()
        )

        return {
            "event_id": created.get("id", ""),
            "html_link": created.get("htmlLink", ""),
            "title": title,
            "start_utc": start_utc,
        }
    except CalendarAPIError:
        raise
    except Exception as exc:
        raise CalendarAPIError(f"create_event failed: {exc}") from exc


def send_invite(event_id: str, participants: list[str]) -> dict[str, Any]:
    """
    Patch attendees and trigger invitation notifications.
    """
    try:
        service = _get_service()
        attendees = [{"email": email} for email in participants]
        (
            service.events()
            .patch(
                calendarId="primary",
                eventId=event_id,
                body={"attendees": attendees},
                sendUpdates="all",
            )
            .execute()
        )
        return {"invited": participants, "event_id": event_id}
    except CalendarAPIError:
        raise
    except Exception as exc:
        raise CalendarAPIError(f"send_invite failed: {exc}") from exc
