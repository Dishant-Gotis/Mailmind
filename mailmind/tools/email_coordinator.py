"""
Email coordination tool functions used by the Phase 5 tool registry.
"""

from __future__ import annotations

import re
from datetime import timedelta
from typing import Any

import dateparser
from dateparser.search import search_dates
import pytz

from checkpointer import load_state
from logger import get_logger
from smtp_sender import send_reply as smtp_send_reply

logger = get_logger(__name__)

VALID_INTENTS = {"scheduling", "update_request", "reschedule", "cancellation", "noise"}


def classify(body: str, subject: str, intent: str, confidence: float) -> dict[str, Any]:
    """
    Return the model-provided intent payload with guardrails.
    """
    if intent not in VALID_INTENTS:
        logger.warning("Invalid intent '%s' returned by model. Falling back to noise.", intent)
        return {"intent": "noise", "confidence": 0.0}

    return {
        "intent": intent,
        "confidence": float(confidence),
    }


def parse_availability(text: str, sender_tz: str = "UTC") -> dict[str, Any]:
    """
    Parse free-form availability text into UTC slots.
    """
    tz_obj = _get_tz(sender_tz)
    tz_name = getattr(tz_obj, "zone", "UTC")

    settings = {
        "PREFER_DATES_FROM": "future",
        "RETURN_AS_TIMEZONE_AWARE": True,
        "TIMEZONE": tz_name,
        "TO_TIMEZONE": "UTC",
    }

    slots: list[dict[str, str]] = []
    for raw_text, parsed_dt in search_dates(text, settings=settings) or []:
        if parsed_dt is None:
            continue

        if parsed_dt.tzinfo is None:
            parsed_dt = tz_obj.localize(parsed_dt)
        start_utc = parsed_dt.astimezone(pytz.utc)
        end_utc = start_utc + timedelta(hours=1)

        slots.append(
            {
                "start_utc": start_utc.isoformat(),
                "end_utc": end_utc.isoformat(),
                "participant": "",
                "raw_text": raw_text,
                "timezone": tz_name,
            }
        )

    logger.debug("Parsed %d availability slot(s).", len(slots))
    return {"slots": slots, "count": len(slots)}


def detect_ambiguity(text: str) -> dict[str, Any]:
    """
    Detect vague or non-actionable availability text.
    """
    vague_patterns = [
        r"\bsometime\b",
        r"\bsome time\b",
        r"\bwhenever\b",
        r"\bany ?time\b",
        r"\bflexible\b",
        r"\bmornings?\b",
        r"\bafternoons?\b",
        r"\bevenings?\b",
        r"\bsoon\b",
        r"\bnext week\b(?!\s+\w+day)",
        r"\bthis week\b(?!\s+\w+day)",
    ]

    for pattern in vague_patterns:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return {
                "is_ambiguous": True,
                "question": (
                    "Could you share 2-3 specific times when you are available? "
                    "Example: Monday 07 Apr 10:00-11:00 IST, Tuesday 08 Apr 14:00-15:00 IST."
                ),
            }

    parsed = parse_availability(text=text, sender_tz="UTC")
    if parsed["count"] == 0:
        return {
            "is_ambiguous": True,
            "question": (
                "I could not extract specific times from your message. "
                "Please share availability as: Day DD Mon HH:MM-HH:MM Timezone."
            ),
        }

    return {"is_ambiguous": False, "question": ""}


def get_thread_history(thread_id: str) -> dict[str, Any]:
    """
    Return history entries persisted in session state for the thread.
    """
    state = load_state(thread_id)
    if state is None:
        return {"thread_id": thread_id, "history": [], "count": 0}

    history = state.get("history", [])
    return {"thread_id": thread_id, "history": history, "count": len(history)}


def send_reply(
    to: str,
    subject: str,
    body: str,
    thread_id: str,
    in_reply_to: str = "",
    references: str = "",
    cc: list[str] | None = None,
) -> dict[str, Any]:
    """
    Send reply via smtp_sender; disclaimer is appended in smtp_sender.
    """
    smtp_send_reply(
        to=to,
        subject=subject,
        body=body,
        thread_id=thread_id,
        in_reply_to=in_reply_to,
        references=references,
        cc=cc,
    )
    return {"sent": True, "to": to, "subject": subject}


def _get_tz(tz_string: str):
    """
    Resolve timezone safely, defaulting to UTC if unknown.
    """
    try:
        return pytz.timezone(tz_string)
    except pytz.exceptions.UnknownTimeZoneError:
        logger.warning("Unknown timezone '%s'. Falling back to UTC.", tz_string)
        return pytz.utc
