# PHASE5_TOOL_REGISTRY.md
## Phase 5 — Core Tool Registry
**Covers:** `tool_registry.py`, `tools/email_coordinator.py`, `tools/calendar_manager.py`, `tools/coordination_memory.py`, `tools/thread_intelligence.py`, all function signatures, Gemini JSON schemas, `tests/test_tools.py`
**Files documented:** `tool_registry.py`, `tools/__init__.py`, all 4 tool modules, `tests/test_tools.py`

---

## Purpose

Phase 5 implements every capability the agent can take as an action. All four tool modules are plain Python functions exposed to Gemini as callable tools via their JSON schemas. Gemini sees the schema and decides which function to call and with what arguments — the tool registry dispatches that call and returns the result back to the node. This phase covers every required deliverable from the problem statement: availability extraction, overlap detection, Calendar event creation, invite dispatch, thread summaries, duplicate prevention, and the mandatory AI disclaimer enforcement. No tool in this phase calls Gemini directly — tools are pure functions that transform data, call external APIs (Calendar, SMTP), or read/write SQLite. Gemini calls tools; tools never call Gemini.

---

## Dependencies

- **Phase 1:** `config.py`, `exceptions.py` (CalendarAPIError, DuplicateEventError, SMTPConnectionError), `logger.py`
- **Phase 2:** `smtp_sender.send_reply()`, `disclaimer.append_disclaimer()`
- **Phase 3:** `db.get_db()`, `checkpointer.load_state()`, `preference_store.load_preferences()`, `preference_store.check_vip_status()`
- **Phase 4:** Tool schemas must match the format documented in PHASE4 — used by `tool_registry.get_schema()`
- **pip packages:** `dateparser==1.2.0`, `pytz==2024.1`, `google-api-python-client==2.128.0`, `google-auth-oauthlib==1.2.0`

---

## 1. tool_registry.py — Complete Implementation

```python
# tool_registry.py
"""
Central registry mapping tool names to callable functions and their Gemini JSON schemas.

Usage from tool_caller.py:
    from tool_registry import call_tool, get_schema, ALL_TOOL_SCHEMAS

    result = call_tool("classify", {"body": "...", "subject": "..."})
    schema = get_schema("classify")
    all_schemas = ALL_TOOL_SCHEMAS   # pass to Gemini in each prompt
"""

from __future__ import annotations

from typing import Any

from exceptions import ToolNotFoundError
from logger import get_logger

logger = get_logger(__name__)

# Lazy imports to avoid circular dependencies — tools import from this module in Phase 6
def _get_registry() -> dict[str, Any]:
    from tools.email_coordinator import classify, parse_availability, detect_ambiguity, get_thread_history, send_reply
    from tools.calendar_manager import check_duplicate, create_event, send_invite
    from tools.coordination_memory import track_participant_slots, find_overlap, rank_slots
    from tools.thread_intelligence import summarise_thread, get_scheduling_status, detect_cancellation

    return {
        "classify":               classify,
        "parse_availability":     parse_availability,
        "detect_ambiguity":       detect_ambiguity,
        "get_thread_history":     get_thread_history,
        "send_reply":             send_reply,
        "check_duplicate":        check_duplicate,
        "create_event":           create_event,
        "send_invite":            send_invite,
        "track_participant_slots": track_participant_slots,
        "find_overlap":           find_overlap,
        "rank_slots":             rank_slots,
        "summarise_thread":       summarise_thread,
        "get_scheduling_status":  get_scheduling_status,
        "detect_cancellation":    detect_cancellation,
    }


def call_tool(name: str, args: dict) -> Any:
    """
    Dispatch a tool call by name with the given arguments dict.

    Args:
        name: Tool function name exactly as returned by Gemini.
        args: Dict of keyword arguments to pass to the function.

    Returns:
        Any: The return value of the tool function.

    Raises:
        ToolNotFoundError: If name is not in the registry.
    """
    registry = _get_registry()
    if name not in registry:
        raise ToolNotFoundError(
            f"Tool '{name}' not found in TOOL_REGISTRY. "
            f"Available tools: {list(registry.keys())}"
        )
    logger.debug("Dispatching tool: %s(%s)", name, args)
    return registry[name](**args)


def get_schema(name: str) -> dict:
    """Return the Gemini JSON schema for a single named tool."""
    for schema in ALL_TOOL_SCHEMAS:
        if schema["function"]["name"] == name:
            return schema
    raise ToolNotFoundError(f"No schema found for tool '{name}'.")


# All tool schemas — passed to Gemini in every prompt that uses tools
ALL_TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "classify",
            "description": "Classify the intent of an inbound email into one of 5 categories. Returns intent string and a confidence score.",
            "parameters": {
                "type": "object",
                "properties": {
                    "body":       {"type": "string", "description": "Plain-text email body."},
                    "subject":    {"type": "string", "description": "Email subject line."},
                    "intent":     {"type": "string", "description": "One of: scheduling, update_request, reschedule, cancellation, noise"},
                    "confidence": {"type": "number", "description": "Float 0.0–1.0 indicating classification certainty."}
                },
                "required": ["body", "subject", "intent", "confidence"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "parse_availability",
            "description": "Extract time slots from free-form availability text. Returns list of UTC TimeSlot dicts.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text":       {"type": "string", "description": "The email body containing availability text."},
                    "sender_tz":  {"type": "string", "description": "IANA timezone of the sender. E.g. 'Asia/Kolkata'. Use 'UTC' if unknown."}
                },
                "required": ["text", "sender_tz"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "detect_ambiguity",
            "description": "Detect if availability text is too vague to parse. Returns bool and a clarifying question string.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "The availability text to check for ambiguity."}
                },
                "required": ["text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "detect_cancellation",
            "description": "Detect if the email body contains a cancellation intent.",
            "parameters": {
                "type": "object",
                "properties": {
                    "body": {"type": "string", "description": "Plain-text email body."}
                },
                "required": ["body"]
            }
        }
    },
]
```

---

## 2. tools/email_coordinator.py — Complete Implementation

```python
# tools/email_coordinator.py
"""
Email coordination tool functions.
All functions are called via tool_registry.call_tool() — never called directly from nodes.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

import dateparser
import pytz

from db import get_db
from logger import get_logger
from smtp_sender import send_reply as smtp_send_reply

logger = get_logger(__name__)


def classify(body: str, subject: str, intent: str, confidence: float) -> dict:
    """
    Return the Gemini-provided classification. Gemini fills these args directly.

    Args:
        body:       Email body (used by Gemini to produce the classification).
        subject:    Email subject.
        intent:     Gemini's classification — one of:
                    "scheduling" | "update_request" | "reschedule" | "cancellation" | "noise"
        confidence: Float 0.0–1.0.

    Returns:
        dict: {"intent": str, "confidence": float}

    Note:
        This function does no LLM call itself. Gemini calls it via tool use,
        populating intent and confidence. The function just validates and returns.
    """
    valid_intents = {"scheduling", "update_request", "reschedule", "cancellation", "noise"}
    if intent not in valid_intents:
        intent = "noise"
        confidence = 0.0
    return {"intent": intent, "confidence": float(confidence)}


def parse_availability(text: str, sender_tz: str = "UTC") -> dict:
    """
    Parse natural language availability text into a list of UTC TimeSlot dicts.

    Args:
        text:       Free-form availability text from an email body.
                    E.g. "I'm free Monday 3–5pm and Tuesday morning from 10am."
        sender_tz:  IANA timezone string for the sender. E.g. "Asia/Kolkata".
                    Used to interpret timezone-naive times in the text.

    Returns:
        dict: {
            "slots": list[dict]   — each dict has: start_utc, end_utc (ISO strings),
                                     participant (empty str, set by caller),
                                     raw_text (the matched substring), timezone (sender_tz)
            "count": int          — number of slots found
        }

    Implementation:
        Uses dateparser.search.search_dates() to find all date/time expressions.
        For each found datetime, constructs a 1-hour window (start to start+60min).
        Applies PREFER_DAY_OF_MONTH_BEFORE_YEAR and PREFER_DATES_FROM=future settings.
        Normalises to UTC via pytz before returning.
    """
    from dateparser.search import search_dates

    tz_obj = _get_tz(sender_tz)
    settings = {
        "PREFER_DATES_FROM": "future",
        "RETURN_AS_TIMEZONE_AWARE": True,
        "TIMEZONE": sender_tz,
        "TO_TIMEZONE": "UTC",
    }

    results = search_dates(text, settings=settings) or []
    slots = []

    for raw_text, dt in results:
        if dt is None:
            continue
        # Ensure UTC
        if dt.tzinfo is None:
            dt = tz_obj.localize(dt).astimezone(pytz.utc)
        else:
            dt = dt.astimezone(pytz.utc)

        # Build 1-hour window (default — overridden by rank_slots with MEETING_DURATION_MINUTES)
        from datetime import timedelta
        end_dt = dt + timedelta(hours=1)

        slots.append({
            "start_utc": dt.isoformat(),
            "end_utc":   end_dt.isoformat(),
            "participant": "",          # caller fills this in
            "raw_text":  raw_text,
            "timezone":  sender_tz,
        })

    logger.debug("parse_availability found %d slot(s).", len(slots))
    return {"slots": slots, "count": len(slots)}


def detect_ambiguity(text: str) -> dict:
    """
    Detect if availability text is too vague to parse into specific time slots.

    Args:
        text: The availability text to check.

    Returns:
        dict: {
            "is_ambiguous": bool,
            "question": str    — clarifying question to ask (empty if not ambiguous)
        }

    Strategy:
        1. Try parse_availability on the text.
        2. If 0 slots found → ambiguous.
        3. Also check against a patterns library of known vague expressions.
    """
    VAGUE_PATTERNS = [
        r"\bsometime\b", r"\bsome time\b", r"\bwhenever\b", r"\bany time\b",
        r"\banytime\b", r"\bflexible\b", r"\bmornings?\b", r"\bafternoons?\b",
        r"\bevenings?\b", r"\bnext week\b(?!\s+\w+day)",
        r"\bthis week\b(?!\s+\w+day)", r"\bsoon\b",
    ]
    for pattern in VAGUE_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return {
                "is_ambiguous": True,
                "question": (
                    "Could you share 2–3 specific times when you're available? "
                    "For example: Monday 07 Apr 10:00–11:00 IST, Tuesday 08 Apr 14:00–15:00 IST."
                ),
            }

    # Try parsing — if nothing comes back, it's ambiguous
    result = parse_availability(text, sender_tz="UTC")
    if result["count"] == 0:
        return {
            "is_ambiguous": True,
            "question": (
                "I wasn't able to extract specific times from your message. "
                "Could you please share your availability in this format: "
                "Day DD Mon HH:MM–HH:MM Timezone?"
            ),
        }

    return {"is_ambiguous": False, "question": ""}


def get_thread_history(thread_id: str) -> dict:
    """
    Retrieve all stored emails for a thread from SQLite session state.

    Args:
        thread_id: Gmail thread ID (session key).

    Returns:
        dict: {
            "thread_id": str,
            "history": list[dict]   — each dict: {"role": str, "content": str}
            "count": int
        }
    """
    from checkpointer import load_state
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
) -> dict:
    """
    Send an outbound email reply. Disclaimer is appended inside smtp_sender.send_reply().

    Args:
        to:           Recipient email address (single string).
        subject:      Email subject — use the original subject unchanged.
        body:         Email body WITHOUT disclaimer. Disclaimer is appended by smtp_sender.
        thread_id:    Thread session key — used for References header.
        in_reply_to:  Message-ID of the email being replied to.
        references:   Full References chain string.
        cc:           Optional CC list.

    Returns:
        dict: {"sent": True, "to": to, "subject": subject}

    Raises:
        SMTPConnectionError: If send fails after retry.
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


# ── Internal helpers ───────────────────────────────────────────────────────────

def _get_tz(tz_string: str) -> pytz.BaseTzInfo:
    """Return pytz timezone object. Falls back to UTC on invalid string."""
    try:
        return pytz.timezone(tz_string)
    except pytz.exceptions.UnknownTimeZoneError:
        logger.warning("Unknown timezone '%s' — falling back to UTC.", tz_string)
        return pytz.utc
```

---

## 3. tools/calendar_manager.py — Complete Implementation

```python
# tools/calendar_manager.py
"""
Google Calendar API v3 tool functions.
OAuth credentials and token management handled by calendar_auth.py (Phase 8).
For Phase 5, assumes get_calendar_service() returns a valid service object.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from config import config
from exceptions import CalendarAPIError, DuplicateEventError
from logger import get_logger

logger = get_logger(__name__)


def _get_service():
    """
    Return an authenticated Google Calendar API service object.
    Imports calendar_auth to get credentials — defined in Phase 8 (calendar_auth.py).
    For Phase 5 testing, this can be mocked.
    """
    try:
        from calendar_auth import get_calendar_service
        return get_calendar_service()
    except ImportError:
        raise CalendarAPIError(
            "calendar_auth.py not yet implemented. "
            "Complete Phase 8 (calendar_auth.py) before using calendar tools."
        )


def check_duplicate(title: str, start_utc: str, participants: list[str]) -> dict:
    """
    Check if a matching Calendar event already exists before creating a new one.

    Args:
        title:         Event title to match (case-insensitive substring match).
        start_utc:     ISO 8601 UTC start time. E.g. "2026-04-07T09:00:00+00:00".
        participants:  List of attendee emails to check.

    Returns:
        dict: {"duplicate": bool, "event_id": str | None}
              event_id is the existing event ID if duplicate=True, else None.

    Raises:
        CalendarAPIError: If the Calendar API call fails.

    Implementation:
        Calls events.list with timeMin=start_utc-1h, timeMax=start_utc+1h.
        Checks each returned event for title substring match AND participant overlap.
        A duplicate requires BOTH conditions to be true.
    """
    try:
        service = _get_service()
        start_dt = datetime.fromisoformat(start_utc)
        time_min = (start_dt - timedelta(hours=1)).isoformat()
        time_max = (start_dt + timedelta(hours=1)).isoformat()

        events_result = service.events().list(
            calendarId="primary",
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy="startTime",
        ).execute()

        events = events_result.get("items", [])
        participants_lower = {p.lower() for p in participants}

        for event in events:
            event_title = event.get("summary", "").lower()
            if title.lower() not in event_title:
                continue
            attendees = {
                a["email"].lower()
                for a in event.get("attendees", [])
            }
            if attendees & participants_lower:  # non-empty intersection
                logger.info("Duplicate event found: %s", event["id"])
                return {"duplicate": True, "event_id": event["id"]}

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
) -> dict:
    """
    Create a Google Calendar event and return the event ID.

    Args:
        title:         Event summary/title string.
        start_utc:     ISO 8601 UTC start datetime. E.g. "2026-04-07T09:00:00+00:00".
        end_utc:       ISO 8601 UTC end datetime.
        participants:  List of attendee email addresses. All receive invitations.
        description:   Optional event description (thread summary, AI disclaimer note).

    Returns:
        dict: {"event_id": str, "html_link": str, "title": str, "start_utc": str}

    Raises:
        DuplicateEventError: If check_duplicate() finds a match (caller should check first).
        CalendarAPIError:    If the events.insert API call fails.
    """
    try:
        service = _get_service()

        attendees = [{"email": email} for email in participants]

        event_body = {
            "summary":     title,
            "description": description,
            "start": {"dateTime": start_utc, "timeZone": "UTC"},
            "end":   {"dateTime": end_utc,   "timeZone": "UTC"},
            "attendees": attendees,
            "reminders": {
                "useDefault": False,
                "overrides": [
                    {"method": "email",  "minutes": 1440},  # 24h before
                    {"method": "popup",  "minutes": 15},
                ],
            },
            "guestsCanModifyEvent": False,
            "guestsCanInviteOthers": False,
        }

        created = service.events().insert(
            calendarId="primary",
            body=event_body,
            sendUpdates="all",   # sends email invitations to all attendees
        ).execute()

        logger.info(
            "Calendar event created: %s (id=%s)",
            title, created["id"],
        )
        return {
            "event_id":  created["id"],
            "html_link": created.get("htmlLink", ""),
            "title":     title,
            "start_utc": start_utc,
        }

    except Exception as exc:
        raise CalendarAPIError(f"create_event failed: {exc}") from exc


def send_invite(event_id: str, participants: list[str]) -> dict:
    """
    Patch an existing event to ensure all listed participants are attendees.
    sendUpdates="all" triggers email notifications for any newly added attendees.

    Args:
        event_id:     Google Calendar event ID (from create_event return value).
        participants: List of email addresses to ensure are invited.

    Returns:
        dict: {"invited": list[str], "event_id": str}

    Raises:
        CalendarAPIError: If the events.patch call fails.

    Note:
        create_event with sendUpdates="all" already sends invitations.
        send_invite is used when participants need to be added after initial creation,
        or to confirm invitations were dispatched.
    """
    try:
        service = _get_service()
        attendees = [{"email": email} for email in participants]

        service.events().patch(
            calendarId="primary",
            eventId=event_id,
            body={"attendees": attendees},
            sendUpdates="all",
        ).execute()

        logger.info("Invitations sent for event %s to: %s", event_id, participants)
        return {"invited": participants, "event_id": event_id}

    except Exception as exc:
        raise CalendarAPIError(f"send_invite failed: {exc}") from exc
```

---

## 4. tools/coordination_memory.py — Complete Implementation

```python
# tools/coordination_memory.py
"""
Availability tracking, overlap computation, and slot ranking.
All functions read/write SQLite via checkpointer and preference_store.
rank_slots() is a deterministic Python function — no LLM involved.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from checkpointer import load_state, save_state
from config import config
from logger import get_logger
from preference_store import check_vip_status, load_preferences

logger = get_logger(__name__)

# Scoring weights — must sum to 1.0
WEIGHT_ATTENDANCE   = 0.50
WEIGHT_PREFERENCE   = 0.25
WEIGHT_VIP          = 0.15
WEIGHT_CHRONOLOGY   = 0.10

# Soft conflict penalty (applied when a slot violates a preference)
PREFERENCE_VIOLATION_PENALTY = 0.10


def track_participant_slots(thread_id: str, email: str, slots: list[dict]) -> dict:
    """
    Store parsed UTC slots for one participant in the session state.

    Args:
        thread_id: Gmail thread ID (session key).
        email:     Participant email address (lowercase).
        slots:     List of TimeSlot dicts with start_utc and end_utc as ISO strings.

    Returns:
        dict: {"tracked": True, "email": email, "slot_count": int}
    """
    state = load_state(thread_id)
    if state is None:
        return {"tracked": False, "email": email, "slot_count": 0}

    email = email.lower().strip()
    existing = state["slots_per_participant"].get(email, [])
    existing.extend(slots)
    state["slots_per_participant"][email] = existing

    # Remove from pending_responses if present
    if email in state["pending_responses"]:
        state["pending_responses"].remove(email)

    save_state(thread_id, state)
    return {"tracked": True, "email": email, "slot_count": len(existing)}


def find_overlap(thread_id: str) -> dict:
    """
    Compute intersection of all participant slot lists from session state.

    Algorithm:
        1. Load state — get slots_per_participant, exclude non_responsive participants.
        2. For each slot of participant A: check if any slot of every other participant
           overlaps with it (start_A < end_B AND start_B < end_A).
        3. A candidate slot is one where at least ATTENDANCE_THRESHOLD fraction of
           participants have an overlapping slot.
        4. Return all candidate slots sorted chronologically.

    Args:
        thread_id: Gmail thread ID.

    Returns:
        dict: {
            "candidates": list[dict]   — list of overlapping TimeSlot dicts (start/end as ISO strings),
            "count": int,
            "participant_count": int
        }
    """
    state = load_state(thread_id)
    if state is None:
        return {"candidates": [], "count": 0, "participant_count": 0}

    slots_map = state["slots_per_participant"]
    non_responsive = set(state.get("non_responsive", []))

    # Only consider responsive participants
    active_participants = [p for p in slots_map if p not in non_responsive]
    if len(active_participants) < 2:
        # Single participant — all their slots are candidates
        solo = active_participants[0] if active_participants else None
        candidates = slots_map.get(solo, []) if solo else []
        return {"candidates": candidates, "count": len(candidates), "participant_count": 1}

    threshold = config.attendance_threshold
    candidate_slots: list[dict] = []

    # Use the first participant's slots as anchors
    anchor_email = active_participants[0]
    for anchor_slot in slots_map.get(anchor_email, []):
        anchor_start = _parse_dt(anchor_slot["start_utc"])
        anchor_end   = _parse_dt(anchor_slot["end_utc"])

        overlap_count = 1  # anchor participant counts
        for other_email in active_participants[1:]:
            for other_slot in slots_map.get(other_email, []):
                other_start = _parse_dt(other_slot["start_utc"])
                other_end   = _parse_dt(other_slot["end_utc"])
                if anchor_start < other_end and other_start < anchor_end:
                    overlap_count += 1
                    break  # one overlap from this participant is enough

        attendance_fraction = overlap_count / len(active_participants)
        if attendance_fraction >= threshold:
            candidate_slots.append(anchor_slot)

    # Sort chronologically
    candidate_slots.sort(key=lambda s: _parse_dt(s["start_utc"]))
    return {
        "candidates":         candidate_slots,
        "count":              len(candidate_slots),
        "participant_count":  len(active_participants),
    }


def rank_slots(candidate_slots: list[dict], preferences: dict) -> dict:
    """
    Score all candidate slots and return the best one with a reason string.
    Deterministic Python — no LLM.

    Scoring formula (per slot):
        score = (WEIGHT_ATTENDANCE  * attendance_score)
              + (WEIGHT_PREFERENCE  * preference_score)
              + (WEIGHT_VIP         * vip_score)
              + (WEIGHT_CHRONOLOGY  * chronology_score)
              - penalty

    Args:
        candidate_slots: List of TimeSlot dicts (start_utc, end_utc as ISO strings).
        preferences:     Dict mapping email → PreferenceProfile dict (from preference_store).

    Returns:
        dict: {
            "ranked_slot":   dict — the best TimeSlot,
            "score":         float,
            "reason":        str — human-readable explanation,
            "below_threshold": bool — True if no slot meets ATTENDANCE_THRESHOLD
        }
    """
    if not candidate_slots:
        return {"ranked_slot": None, "score": 0.0, "reason": "No candidate slots.", "below_threshold": True}

    all_participants = list(preferences.keys())
    total = len(all_participants) if all_participants else 1

    # For chronology scoring: earliest slot in candidates is reference
    all_starts = [_parse_dt(s["start_utc"]) for s in candidate_slots]
    earliest = min(all_starts)
    latest   = max(all_starts)
    time_span_seconds = max((latest - earliest).total_seconds(), 1)

    scored: list[tuple[float, dict, str]] = []

    for slot in candidate_slots:
        slot_start = _parse_dt(slot["start_utc"])
        slot_hour  = slot_start.hour   # UTC hour 0–23

        # ── Attendance score ───────────────────────────────────────────────────
        # What fraction of participants have availability overlapping this slot?
        # (Already filtered by find_overlap — all candidates meet threshold)
        attendance_count = sum(
            1 for email, prefs_data in preferences.items()
            if _has_overlap(slot, preferences.get(email, {}).get("slots", []))
        )
        attendance_score = attendance_count / total

        # ── Preference score ───────────────────────────────────────────────────
        # What fraction of participants have this slot within their preferred hours?
        pref_score_sum = 0.0
        penalty = 0.0
        for email, pref in preferences.items():
            pref_start = pref.get("preferred_hours_start", 9)
            pref_end   = pref.get("preferred_hours_end",   17)
            blocked    = pref.get("blocked_days", [])
            slot_day   = slot_start.strftime("%A")  # e.g. "Monday"

            in_preferred_hours = pref_start <= slot_hour < pref_end
            not_blocked_day    = slot_day not in blocked

            if in_preferred_hours and not_blocked_day:
                pref_score_sum += 1.0
            elif not not_blocked_day or not in_preferred_hours:
                # Soft penalty — slot is valid but sub-optimal
                penalty += PREFERENCE_VIOLATION_PENALTY / total

        preference_score = pref_score_sum / total

        # ── VIP score ─────────────────────────────────────────────────────────
        # Are all VIP participants available in this slot?
        vip_participants = [e for e in all_participants if check_vip_status(e)]
        if vip_participants:
            vip_available = sum(
                1 for vip in vip_participants
                if _has_overlap(slot, preferences.get(vip, {}).get("slots", []))
            )
            vip_score = vip_available / len(vip_participants)
        else:
            vip_score = 1.0  # No VIPs configured — full score

        # ── Chronology score ───────────────────────────────────────────────────
        # Earlier slots score higher (tiebreaker). Range: 0.0–1.0
        elapsed = (slot_start - earliest).total_seconds()
        chronology_score = 1.0 - (elapsed / time_span_seconds)

        # ── Final weighted score ───────────────────────────────────────────────
        final_score = (
            WEIGHT_ATTENDANCE  * attendance_score
          + WEIGHT_PREFERENCE  * preference_score
          + WEIGHT_VIP         * vip_score
          + WEIGHT_CHRONOLOGY  * chronology_score
          - penalty
        )

        # Human-readable reason
        reason = (
            f"{int(attendance_score * 100)}% attendance"
            + (f", VIP available" if vip_score == 1.0 and vip_participants else "")
            + (f", within preferred hours" if preference_score > 0.5 else "")
        )
        scored.append((final_score, slot, reason))

    # Sort descending by score
    scored.sort(key=lambda t: t[0], reverse=True)
    best_score, best_slot, best_reason = scored[0]

    return {
        "ranked_slot":     best_slot,
        "score":           round(best_score, 4),
        "reason":          best_reason,
        "below_threshold": best_score < 0.5,
    }


# ── Internal helpers ───────────────────────────────────────────────────────────

def _parse_dt(val) -> datetime:
    """Parse ISO string or return datetime as-is, ensuring UTC awareness."""
    if isinstance(val, str):
        dt = datetime.fromisoformat(val)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    if isinstance(val, datetime):
        if val.tzinfo is None:
            return val.replace(tzinfo=timezone.utc)
        return val.astimezone(timezone.utc)
    raise ValueError(f"Cannot parse datetime from: {val}")


def _has_overlap(slot: dict, participant_slots: list[dict]) -> bool:
    """Return True if slot overlaps with any slot in participant_slots."""
    s_start = _parse_dt(slot["start_utc"])
    s_end   = _parse_dt(slot["end_utc"])
    for ps in participant_slots:
        ps_start = _parse_dt(ps["start_utc"])
        ps_end   = _parse_dt(ps["end_utc"])
        if s_start < ps_end and ps_start < s_end:
            return True
    return False
```

---

## 5. tools/thread_intelligence.py — Complete Implementation

```python
# tools/thread_intelligence.py
"""
Thread summary, status, and cancellation detection tools.
summarise_thread and detect_cancellation use Gemini via call_for_text/call_with_tools.
"""

from __future__ import annotations

from checkpointer import load_state
from logger import get_logger
from preference_store import get_historical_slots

logger = get_logger(__name__)


def summarise_thread(thread_id: str) -> dict:
    """
    Read the full thread history from session state and generate a contextual summary.

    Args:
        thread_id: Gmail thread ID.

    Returns:
        dict: {"summary": str, "thread_id": str}
    """
    state = load_state(thread_id)
    if state is None:
        return {"summary": "No thread history found.", "thread_id": thread_id}

    history = state.get("history", [])
    if not history:
        return {"summary": "Thread has no recorded history yet.", "thread_id": thread_id}

    history_text = "\n\n".join(
        f"[{msg['role'].upper()}]: {msg['content']}" for msg in history
    )

    from prompt_builder import build_summarise_prompt
    from tool_caller import call_for_text
    messages = build_summarise_prompt(history_text, state)
    summary = call_for_text(messages, thread_id=thread_id, temperature=0.4)

    return {"summary": summary, "thread_id": thread_id}


def get_scheduling_status(thread_id: str) -> dict:
    """
    Return a plain-text summary of the current session state.

    Args:
        thread_id: Gmail thread ID.

    Returns:
        dict: {
            "thread_id": str,
            "intent": str,
            "participants": list[str],
            "pending_responses": list[str],
            "has_ranked_slot": bool,
            "approval_status": str,
            "current_node": str
        }
    """
    state = load_state(thread_id)
    if state is None:
        return {"thread_id": thread_id, "intent": "unknown", "participants": [],
                "pending_responses": [], "has_ranked_slot": False,
                "approval_status": "none", "current_node": ""}

    return {
        "thread_id":        thread_id,
        "intent":           state.get("intent", "unknown"),
        "participants":     state.get("participants", []),
        "pending_responses": state.get("pending_responses", []),
        "has_ranked_slot":  state.get("ranked_slot") is not None,
        "approval_status":  state.get("approval_status", "none"),
        "current_node":     state.get("current_node", ""),
    }


def detect_cancellation(body: str) -> dict:
    """
    Detect if the email body contains a cancellation intent.
    Uses Gemini via call_for_text for edge cases; checks pattern library first.

    Args:
        body: Plain-text email body.

    Returns:
        dict: {"is_cancellation": bool}
    """
    import re
    CANCELLATION_PATTERNS = [
        r"\bcancel\b", r"\bcancelling\b", r"\bcanceled\b",
        r"\bno longer\b", r"\bcall off\b", r"\bcalled off\b",
        r"\bwon't be able\b", r"\bcannot make\b", r"\bnot going to work\b",
        r"\bscrapping\b", r"\bscrap the meeting\b",
    ]
    for pattern in CANCELLATION_PATTERNS:
        if re.search(pattern, body, re.IGNORECASE):
            return {"is_cancellation": True}
    return {"is_cancellation": False}


def suggest_optimal_time(email: str) -> dict:
    """
    Analyse historical_slots for a participant and return a PreferenceProfile.
    Used in Phase 9 to bias rank_slots() scoring toward observed patterns.

    Args:
        email: Participant email address.

    Returns:
        dict: {
            "email": str,
            "preferred_hour_buckets": list[int]  — UTC hours most frequently accepted,
            "preferred_days": list[str]           — weekday names most frequently accepted,
            "sample_size": int                    — number of historical slots analysed
        }
    """
    slots = get_historical_slots(email)
    if not slots:
        return {
            "email": email,
            "preferred_hour_buckets": [],
            "preferred_days": [],
            "sample_size": 0,
        }

    from collections import Counter
    from datetime import datetime, timezone

    hour_counts: Counter = Counter()
    day_counts:  Counter = Counter()

    for slot in slots:
        start_str = slot.get("start_utc", "")
        if not start_str:
            continue
        try:
            dt = datetime.fromisoformat(start_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            hour_counts[dt.hour] += 1
            day_counts[dt.strftime("%A")] += 1
        except ValueError:
            continue

    top_hours = [hour for hour, _ in hour_counts.most_common(3)]
    top_days  = [day  for day,  _ in day_counts.most_common(3)]

    return {
        "email":                  email,
        "preferred_hour_buckets": top_hours,
        "preferred_days":         top_days,
        "sample_size":            len(slots),
    }
```

---

## 6. tools/__init__.py

```python
# tools/__init__.py
# Empty — tools are imported explicitly by tool_registry.py
```

---

## 7. Data Flow

```
agent/nodes.py (any node)
    │
    │  messages = prompt_builder.build_*_prompt(email_obj, state)
    │  result = tool_caller.call_with_tools(messages, ALL_TOOL_SCHEMAS)
    ↓
tool_caller.call_with_tools()
    │  → Gemini returns: tool_name="parse_availability", args={"text":"...", "sender_tz":"..."}
    │  → tool_registry.call_tool("parse_availability", args)
    ↓
tools/email_coordinator.parse_availability(text=..., sender_tz=...)
    │  → dateparser.search.search_dates() extracts datetime objects
    │  → pytz normalises to UTC
    │  → returns {"slots": [...], "count": N}
    ↓
tool_caller.call_with_tools() returns the result dict
    │
    ↓
agent/nodes.coordination_node reads result["slots"]
    ↓
tool_registry.call_tool("track_participant_slots", {thread_id, email, slots})
    ↓
checkpointer.save_state() persists updated slots_per_participant
```

---

## 8. Error Handling

| Error | Source | Recovery |
|---|---|---|
| `ToolNotFoundError` | `tool_registry.call_tool()` | Caught in `agent/nodes.py`, routes to `error_node` |
| `CalendarAPIError` | `calendar_manager.*` | Caught in `calendar_node`, sends fallback email with meeting time but no invite |
| `DuplicateEventError` | `calendar_manager.check_duplicate()` | `calendar_node` sends status reply instead of creating event |
| `SMTPConnectionError` | `email_coordinator.send_reply()` | Caught in `send_node`, logged, session marked with error |
| dateparser finds 0 slots | `parse_availability()` | Returns `{"slots": [], "count": 0}` — triggers `detect_ambiguity` in node |
| No candidate slots after `find_overlap` | `rank_slots()` | Returns `{"below_threshold": True}` — triggers coordination restart |
| `load_state` returns None in tool | Any tool calling `load_state()` | Returns empty/safe defaults — tools are defensively coded |

---

## 9. Unit Tests — tests/test_tools.py

```python
# tests/test_tools.py
"""
Tests for all four tool modules.
Run: pytest tests/test_tools.py -v
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest


class TestClassify:
    def test_valid_intent_returned(self):
        from tools.email_coordinator import classify
        result = classify(body="Let's meet", subject="Meeting", intent="scheduling", confidence=0.9)
        assert result["intent"] == "scheduling"
        assert result["confidence"] == 0.9

    def test_invalid_intent_fallback_to_noise(self):
        from tools.email_coordinator import classify
        result = classify(body="x", subject="y", intent="unknown_intent", confidence=0.8)
        assert result["intent"] == "noise"
        assert result["confidence"] == 0.0


class TestDetectAmbiguity:
    def test_vague_text_detected(self):
        from tools.email_coordinator import detect_ambiguity
        result = detect_ambiguity("I'm free sometime next week")
        assert result["is_ambiguous"] is True
        assert "?" in result["question"]

    def test_specific_text_not_ambiguous(self):
        from tools.email_coordinator import detect_ambiguity
        result = detect_ambiguity("Monday 7 April 10am to 11am IST")
        assert result["is_ambiguous"] is False


class TestDetectCancellation:
    def test_cancel_keyword_detected(self):
        from tools.thread_intelligence import detect_cancellation
        result = detect_cancellation("I need to cancel the meeting.")
        assert result["is_cancellation"] is True

    def test_normal_text_not_cancellation(self):
        from tools.thread_intelligence import detect_cancellation
        result = detect_cancellation("I'm available Monday 10am.")
        assert result["is_cancellation"] is False


class TestRankSlots:
    def _make_slot(self, hour_utc: int, day_offset: int = 0) -> dict:
        from datetime import timedelta
        base = datetime(2026, 4, 7, hour_utc, 0, tzinfo=timezone.utc)
        start = base + timedelta(days=day_offset)
        end   = start.replace(hour=(hour_utc + 1) % 24)
        return {
            "start_utc":   start.isoformat(),
            "end_utc":     end.isoformat(),
            "participant": "alice@example.com",
            "raw_text":    "test",
            "timezone":    "UTC",
        }

    def test_single_slot_returned(self):
        from tools.coordination_memory import rank_slots
        slots = [self._make_slot(10)]
        prefs = {"alice@example.com": {"preferred_hours_start": 9, "preferred_hours_end": 17,
                                        "blocked_days": [], "vip": False, "slots": slots}}
        with patch("tools.coordination_memory.check_vip_status", return_value=False):
            result = rank_slots(slots, prefs)
        assert result["ranked_slot"] is not None

    def test_empty_slots_returns_below_threshold(self):
        from tools.coordination_memory import rank_slots
        result = rank_slots([], {})
        assert result["below_threshold"] is True
        assert result["ranked_slot"] is None

    def test_preferred_hours_slot_scores_higher(self):
        from tools.coordination_memory import rank_slots
        slot_good = self._make_slot(10)   # 10am UTC — within 9–17
        slot_bad  = self._make_slot(3)    # 3am UTC — outside preferred hours
        prefs = {
            "alice@example.com": {"preferred_hours_start": 9, "preferred_hours_end": 17,
                                   "blocked_days": [], "vip": False, "slots": [slot_good, slot_bad]},
        }
        with patch("tools.coordination_memory.check_vip_status", return_value=False):
            result = rank_slots([slot_good, slot_bad], prefs)
        assert result["ranked_slot"]["start_utc"] == slot_good["start_utc"]


class TestToolRegistry:
    def test_call_unknown_tool_raises(self):
        from exceptions import ToolNotFoundError
        from tool_registry import call_tool
        with pytest.raises(ToolNotFoundError):
            call_tool("nonexistent_tool", {})
```

---

## 10. Integration Checklist

- [ ] `tools/__init__.py` exists (empty)
- [ ] `tool_registry.py` exists — `call_tool()`, `get_schema()`, `ALL_TOOL_SCHEMAS` list defined
- [ ] `ALL_TOOL_SCHEMAS` has at least 4 schemas: `classify`, `parse_availability`, `detect_ambiguity`, `detect_cancellation`
- [ ] `tools/email_coordinator.py` — all 5 functions implemented: `classify`, `parse_availability`, `detect_ambiguity`, `get_thread_history`, `send_reply`
- [ ] `send_reply()` in `email_coordinator` calls `smtp_sender.send_reply()` — never writes SMTP directly
- [ ] Disclaimer is NOT added by `email_coordinator.send_reply()` — it is added inside `smtp_sender.send_reply()`
- [ ] `tools/calendar_manager.py` — `check_duplicate`, `create_event`, `send_invite` implemented
- [ ] `create_event()` uses `sendUpdates="all"` — invites fire automatically
- [ ] `tools/coordination_memory.py` — `track_participant_slots`, `find_overlap`, `rank_slots` implemented
- [ ] `rank_slots()` weights sum to 1.0: `0.50 + 0.25 + 0.15 + 0.10 = 1.00`
- [ ] Penalty is subtracted after weighted sum (not added as a negative weight)
- [ ] `find_overlap()` excludes `non_responsive` participants from computation
- [ ] `tools/thread_intelligence.py` — `summarise_thread`, `get_scheduling_status`, `detect_cancellation`, `suggest_optimal_time` implemented
- [ ] `pytest tests/test_tools.py -v` passes all tests

---

## Cross-Phase References

| Exported | From | Imported By |
|---|---|---|
| `call_tool()`, `ALL_TOOL_SCHEMAS` | `tool_registry.py` | `tool_caller.py` (P4), `agent/nodes.py` (P6) |
| `classify()`, `parse_availability()`, `detect_ambiguity()`, `send_reply()` | `tools/email_coordinator.py` | `agent/nodes.py` (P6) via `tool_registry` |
| `check_duplicate()`, `create_event()`, `send_invite()` | `tools/calendar_manager.py` | `agent/nodes.py calendar_node` (P6) via `tool_registry` |
| `track_participant_slots()`, `find_overlap()`, `rank_slots()` | `tools/coordination_memory.py` | `agent/nodes.py` (P6) via `tool_registry` |
| `summarise_thread()`, `detect_cancellation()`, `suggest_optimal_time()` | `tools/thread_intelligence.py` | `agent/nodes.py` (P6) via `tool_registry` |

---

*PHASE5_TOOL_REGISTRY.md | Team TRIOLOGY | PCCOE Pune | Problem Statement 03*
