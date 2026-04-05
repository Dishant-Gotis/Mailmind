"""
Email coordination tool functions used by the Phase 5 tool registry.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
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

    Priority:
    1) Deterministic range parsing (e.g., 4PM-6PM, 14:00-16:00, 4 to 6 PM)
    2) Deterministic single-time parsing (e.g., 5PM UTC)
    3) Guarded dateparser fallback with strict filtering
    """

    tz_obj = _get_tz(sender_tz)
    tz_name = getattr(tz_obj, "zone", "UTC")

    # Ignore quoted thread tails which often contain noisy timestamps.
    clean_text = text.split("\nOn ")[0]
    clean_text = clean_text.split("\n>")[0]

    slots: list[dict[str, str]] = []

    now_utc = datetime.now(pytz.utc)
    base_date = now_utc.date()
    if re.search(r"\btomorrow\b|\btommorow\b", clean_text, flags=re.IGNORECASE):
        base_date = (now_utc + timedelta(days=1)).date()

    def _apply_ampm(hour: int, ampm: str | None) -> int:
        if not ampm:
            return hour
        tag = ampm.lower().replace(".", "")
        if tag == "pm" and hour != 12:
            return hour + 12
        if tag == "am" and hour == 12:
            return 0
        return hour

    # Deterministic range parsing: 4PM-6PM, 4 to 6 PM, 14:00-16:00
    range_pattern = re.compile(
        r"(?P<h1>\d{1,2})(?::(?P<m1>\d{2}))?\s*(?P<a1>a\.m\.|p\.m\.|am|pm)?\s*"
        r"(?:-|to|and)\s*"
        r"(?P<h2>\d{1,2})(?::(?P<m2>\d{2}))?\s*(?P<a2>a\.m\.|p\.m\.|am|pm)?",
        flags=re.IGNORECASE,
    )
    m = range_pattern.search(clean_text)
    if m:
        h1 = int(m.group("h1"))
        m1 = int(m.group("m1") or 0)
        h2 = int(m.group("h2"))
        m2 = int(m.group("m2") or 0)
        a1 = m.group("a1")
        a2 = m.group("a2")

        # If one side has AM/PM, apply it to the other side too.
        if a1 and not a2:
            a2 = a1
        if a2 and not a1:
            a1 = a2

        h1 = _apply_ampm(h1, a1)
        h2 = _apply_ampm(h2, a2)

        try:
            start_dt = tz_obj.localize(datetime.combine(base_date, datetime.min.time()).replace(hour=h1, minute=m1))
            end_dt = tz_obj.localize(datetime.combine(base_date, datetime.min.time()).replace(hour=h2, minute=m2))
            if end_dt <= start_dt:
                end_dt = end_dt + timedelta(days=1)

            slots.append(
                {
                    "start_utc": start_dt.astimezone(pytz.utc).isoformat(),
                    "end_utc": end_dt.astimezone(pytz.utc).isoformat(),
                    "participant": "",
                    "raw_text": m.group(0),
                    "timezone": tz_name,
                }
            )
        except ValueError:
            pass

    # Deterministic single-time parsing if no range found.
    if not slots:
        single_pattern = re.compile(
            r"\b(?P<h>\d{1,2})(?::(?P<m>\d{2}))?\s*(?P<a>a\.m\.|p\.m\.|am|pm)\b",
            flags=re.IGNORECASE,
        )
        sm = single_pattern.search(clean_text)
        if sm:
            h = _apply_ampm(int(sm.group("h")), sm.group("a"))
            mi = int(sm.group("m") or 0)
            try:
                start_dt = tz_obj.localize(datetime.combine(base_date, datetime.min.time()).replace(hour=h, minute=mi))
                end_dt = start_dt + timedelta(hours=1)
                slots.append(
                    {
                        "start_utc": start_dt.astimezone(pytz.utc).isoformat(),
                        "end_utc": end_dt.astimezone(pytz.utc).isoformat(),
                        "participant": "",
                        "raw_text": sm.group(0),
                        "timezone": tz_name,
                    }
                )
            except ValueError:
                pass

    # Guarded fallback with strict filtering.
    if not slots:
        settings = {
            "PREFER_DATES_FROM": "future",
            "RETURN_AS_TIMEZONE_AWARE": True,
            "TIMEZONE": tz_name,
            "TO_TIMEZONE": "UTC",
        }

        max_future = now_utc + timedelta(days=30)

        for raw_text, parsed_dt in search_dates(clean_text, settings=settings) or []:
            if parsed_dt is None:
                continue

            token = raw_text.strip().lower()
            # Ignore short/noisy tokens that often become false positives (e.g., "me", "can").
            if len(token) <= 2 or re.fullmatch(r"[a-z]+", token):
                continue

            if parsed_dt.tzinfo is None:
                parsed_dt = tz_obj.localize(parsed_dt)

            parsed_utc = parsed_dt.astimezone(pytz.utc)
            if not (now_utc <= parsed_utc <= max_future):
                continue

            start_utc = parsed_utc
            end_utc = start_utc + timedelta(hours=1)

            slots.append({
                "start_utc": start_utc.isoformat(),
                "end_utc": end_utc.isoformat(),
                "participant": "",
                "raw_text": raw_text,
                "timezone": tz_name,
            })
    
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


def send_clarification(
    to: str,
    subject: str,
    body: str,
    thread_id: str,
    in_reply_to: str = "",
    references: str = "",
    cc: list[str] | None = None,
) -> dict[str, Any]:
    """
    Send a clarification reply via the same mail path as regular replies.
    """
    return send_reply(
        to=to,
        subject=subject,
        body=body,
        thread_id=thread_id,
        in_reply_to=in_reply_to,
        references=references,
        cc=cc,
    )


def _get_tz(tz_string: str):
    """
    Resolve timezone safely, defaulting to UTC if unknown.
    """
    try:
        return pytz.timezone(tz_string)
    except pytz.exceptions.UnknownTimeZoneError:
        logger.warning("Unknown timezone '%s'. Falling back to UTC.", tz_string)
        return pytz.utc
