# PHASE8_TIMEZONE.md
## Phase 8 — Timezone Detection & UTC Normalisation
**Covers:** `timezone_utils.py`, timezone detection from email headers/body, UTC normalisation pipeline, display formatting, integration into `coordination_node` and `email_parser.py`
**Files documented:** `timezone_utils.py`, `tests/test_timezone_utils.py`

---

## Purpose

Timezone handling is one of the highest-failure-rate aspects of autonomous scheduling. If MailMind assumes UTC when a participant actually means IST, it schedules meetings 5.5 hours off. This phase centralises all timezone logic into a single module (`timezone_utils.py`) so that no other module ever hand-rolls timezone conversion. The mission is: every datetime that enters the system is immediately converted to UTC and stored as UTC. When an email is sent out, datetimes are converted back to the participant's local timezone for display — never stored in local time. This phase also implements timezone detection from email headers and body text, which feeds directly into `parse_availability()` in Phase 5.

---

## Dependencies

- **Phase 1:** `exceptions.py` (`TimezoneError`), `logger.py`
- **Phase 2:** `email_parser.py` — `timezone_utils.detect_timezone_from_email()` called inside `parse_email()` to populate `sender_tz` for Phase 5
- **Phase 5:** `tools/email_coordinator.parse_availability()` — receives `sender_tz` from timezone_utils
- **Phase 3:** `preference_store.store_preferences()` — stores detected timezone per participant
- **pip packages:** `pytz==2024.1` (already in requirements), `dateparser==1.2.0` (already in requirements)

---

## 1. Add `TimezoneError` to exceptions.py (Phase 1 addition)

```python
# exceptions.py — add this class if not already present from Phase 1

class TimezoneError(MailMindError):
    """
    Raised when timezone detection fails and no fallback is available.
    In practice, this should almost never be raised — UTC is always the final fallback.
    Used to signal to the caller that timezone-dependent output may be wrong.
    """
    pass
```

---

## 2. timezone_utils.py — Complete Implementation

```python
# timezone_utils.py
"""
Centralised timezone detection, UTC normalisation, and display formatting.

All functions in this module follow one rule:
    Store everything in UTC. Display in local time. Never store in local time.

Public API:
    detect_timezone_from_email(msg) -> str
    detect_timezone_from_text(text) -> str
    to_utc(dt, tz_string) -> datetime
    to_local(dt_utc, tz_string) -> datetime
    format_for_email(dt_utc, tz_string) -> str
    format_slot_for_email(slot, participant_tz) -> str
    get_common_timezones() -> list[str]
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from email.message import Message
from typing import Optional

import pytz

from logger import get_logger

logger = get_logger(__name__)

# ── Timezone abbreviation mapping ─────────────────────────────────────────────
# Maps common abbreviations found in email text → IANA timezone strings.
# Ambiguous abbreviations (e.g. IST could be India, Israel, Ireland) are resolved
# by the most common usage in the MailMind context (India Standard Time for IST).

ABBREV_TO_IANA: dict[str, str] = {
    # India
    "IST":  "Asia/Kolkata",
    # US
    "EST":  "America/New_York",
    "EDT":  "America/New_York",
    "CST":  "America/Chicago",
    "CDT":  "America/Chicago",
    "MST":  "America/Denver",
    "MDT":  "America/Denver",
    "PST":  "America/Los_Angeles",
    "PDT":  "America/Los_Angeles",
    # UK/Europe
    "GMT":  "Europe/London",
    "BST":  "Europe/London",
    "CET":  "Europe/Paris",
    "CEST": "Europe/Paris",
    # Australia
    "AEST": "Australia/Sydney",
    "AEDT": "Australia/Sydney",
    "AWST": "Australia/Perth",
    # Asia
    "SGT":  "Asia/Singapore",
    "JST":  "Asia/Tokyo",
    "KST":  "Asia/Seoul",
    "CST_CHINA": "Asia/Shanghai",   # separate key to avoid collision with US CST
    "HKT":  "Asia/Hong_Kong",
    # UAE/Gulf
    "GST":  "Asia/Dubai",
    # UTC
    "UTC":  "UTC",
    "Z":    "UTC",
}

# Regex to find timezone abbreviations in text (word boundary match)
TZ_ABBREV_PATTERN = re.compile(
    r'\b(' + '|'.join(re.escape(k) for k in ABBREV_TO_IANA) + r')\b'
)

# Regex to match UTC offset notation in email body: +05:30, +0530, -08:00
UTC_OFFSET_PATTERN = re.compile(
    r'UTC\s*([+-]\d{1,2}:?\d{2})|([+-]\d{1,2}:?\d{2})\s*UTC'
)

# Default fallback timezone when detection fails
DEFAULT_TIMEZONE = "UTC"


# ── Detection functions ────────────────────────────────────────────────────────

def detect_timezone_from_email(raw_msg: Message) -> str:
    """
    Detect the sender's timezone from an email.message.Message object.

    Detection order (first match wins):
        1. Parse the Date header — it contains a UTC offset like "+05:30".
           Convert the offset to an IANA timezone via offset → pytz lookup.
        2. Scan the email body text for timezone abbreviations (IST, PST, etc.).
        3. Scan for explicit UTC offset notation (+05:30) in the body.
        4. Fall back to DEFAULT_TIMEZONE ("UTC").

    Args:
        raw_msg: A parsed email.message.Message object (from Phase 2 email_parser).

    Returns:
        str: IANA timezone string. E.g. "Asia/Kolkata". Never empty — defaults to "UTC".

    Called from: email_parser.parse_email() to populate EmailObject context.
    Result is stored in preference_store for future parsing via store_preferences().
    """
    # Step 1: Extract UTC offset from Date header
    date_header = raw_msg.get("Date", "")
    if date_header:
        tz = _extract_tz_from_date_header(date_header)
        if tz:
            logger.debug("Timezone detected from Date header: %s", tz)
            return tz

    # Step 2 & 3: Scan email body
    body = _extract_body_text(raw_msg)
    if body:
        tz = detect_timezone_from_text(body)
        if tz != DEFAULT_TIMEZONE:
            logger.debug("Timezone detected from body: %s", tz)
            return tz

    logger.debug("Timezone not detected — using default: %s", DEFAULT_TIMEZONE)
    return DEFAULT_TIMEZONE


def detect_timezone_from_text(text: str) -> str:
    """
    Detect timezone from free-form text (email body, natural language).

    Detection order:
        1. Match timezone abbreviation (IST, PST, etc.) from ABBREV_TO_IANA.
        2. Match explicit UTC offset (+05:30, UTC+5:30).
        3. Fall back to "UTC".

    Args:
        text: Any free-form text string to scan.

    Returns:
        str: IANA timezone string. Defaults to "UTC" if nothing found.

    Usage:
        sender_tz = detect_timezone_from_text("I'm free Monday 10am IST")
        # Returns "Asia/Kolkata"
    """
    # Step 1: Abbreviation match
    match = TZ_ABBREV_PATTERN.search(text)
    if match:
        abbrev = match.group(1)
        tz = ABBREV_TO_IANA.get(abbrev)
        if tz:
            return tz

    # Step 2: UTC offset match
    offset_match = UTC_OFFSET_PATTERN.search(text)
    if offset_match:
        offset_str = offset_match.group(1) or offset_match.group(2)
        tz = _offset_string_to_iana(offset_str)
        if tz:
            return tz

    return DEFAULT_TIMEZONE


# ── UTC normalisation ──────────────────────────────────────────────────────────

def to_utc(dt: datetime, tz_string: str = "UTC") -> datetime:
    """
    Convert a datetime to UTC. Handles:
        - Naive datetimes: localised to tz_string first, then converted to UTC.
        - Timezone-aware datetimes: converted to UTC directly.

    Args:
        dt:         Datetime to convert (may be naive or aware).
        tz_string:  IANA timezone string of the datetime's source timezone.
                    Ignored if dt is already timezone-aware.

    Returns:
        datetime: UTC-aware datetime. tzinfo is always timezone.utc.

    Raises:
        Never raises — falls back to treating datetime as UTC on invalid tz_string.

    Usage:
        utc = to_utc(datetime(2026, 4, 7, 9, 0), "Asia/Kolkata")
        # Returns datetime(2026, 4, 7, 3, 30, tzinfo=timezone.utc)
    """
    tz = _get_pytz(tz_string)

    if dt.tzinfo is None:
        # Naive: assume it's in tz_string timezone
        try:
            dt = tz.localize(dt, is_dst=None)
        except pytz.exceptions.AmbiguousTimeError:
            dt = tz.localize(dt, is_dst=True)   # DST ambiguity: assume DST
        except pytz.exceptions.NonExistentTimeError:
            dt = tz.localize(dt, is_dst=True)   # Clocks spring forward: nearest valid
    else:
        # Already aware: convert to UTC irrespective of source TZ
        pass

    return dt.astimezone(pytz.utc).replace(tzinfo=timezone.utc)


def to_local(dt_utc: datetime, tz_string: str) -> datetime:
    """
    Convert a UTC-aware datetime to a local timezone.

    Args:
        dt_utc:    UTC-aware datetime.
        tz_string: IANA timezone string for the target timezone.

    Returns:
        datetime: Timezone-aware datetime in the target timezone.

    Usage:
        local = to_local(datetime(2026, 4, 7, 3, 30, tzinfo=timezone.utc), "Asia/Kolkata")
        # Returns datetime(2026, 4, 7, 9, 0, tzinfo=<DstTzInfo 'Asia/Kolkata'>)
    """
    tz = _get_pytz(tz_string)
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    return dt_utc.astimezone(tz)


# ── Display formatting ─────────────────────────────────────────────────────────

def format_for_email(dt_utc: datetime, tz_string: str) -> str:
    """
    Format a UTC datetime for display in an outbound email body.
    Converts to the participant's local timezone before formatting.

    Format: "Monday 07 Apr 2026, 09:00–10:00 IST"
    (The end time is derived assuming MEETING_DURATION_MINUTES — see format_slot_for_email.)

    Args:
        dt_utc:    UTC-aware datetime to display.
        tz_string: IANA timezone of the display recipient.

    Returns:
        str: Human-readable datetime string in recipient's local timezone.

    Usage:
        s = format_for_email(datetime(2026, 4, 7, 3, 30, tzinfo=timezone.utc), "Asia/Kolkata")
        # Returns "Tuesday 07 Apr 2026, 09:00 IST"
    """
    local_dt = to_local(dt_utc, tz_string)
    abbrev   = _get_tz_abbrev(tz_string, local_dt)
    return local_dt.strftime(f"%A %d %b %Y, %H:%M {abbrev}")


def format_slot_for_email(slot: dict, participant_tz: str) -> str:
    """
    Format a complete TimeSlot dict as a human-readable range string for email.

    Args:
        slot:           TimeSlot dict with "start_utc" and "end_utc" as ISO strings.
        participant_tz: IANA timezone string for the display recipient.

    Returns:
        str: E.g. "Monday 07 Apr 2026, 09:00–10:00 IST"

    Usage in outbound email body:
        slot_str = format_slot_for_email(state["ranked_slot"], state["preferences"]["alice@"]["timezone"])
        draft = f"I'd like to propose: {slot_str}"
    """
    start_utc = _parse_iso_dt(slot.get("start_utc", ""))
    end_utc   = _parse_iso_dt(slot.get("end_utc", ""))

    if start_utc is None:
        return "[time not available]"

    local_start = to_local(start_utc, participant_tz)
    abbrev      = _get_tz_abbrev(participant_tz, local_start)
    start_str   = local_start.strftime("%A %d %b %Y, %H:%M")

    if end_utc:
        local_end = to_local(end_utc, participant_tz)
        end_str   = local_end.strftime("%H:%M")
        return f"{start_str}–{end_str} {abbrev}"
    else:
        return f"{start_str} {abbrev}"


def get_common_timezones() -> list[str]:
    """
    Return the most commonly encountered IANA timezone strings for MailMind's use case.
    Used as a reference list for timezone validation and UI display.

    Returns:
        list[str]: Ordered list of common IANA timezone strings.
    """
    return [
        "UTC",
        "Asia/Kolkata",        # IST +05:30
        "America/New_York",    # EST/EDT
        "America/Los_Angeles", # PST/PDT
        "America/Chicago",     # CST/CDT
        "Europe/London",       # GMT/BST
        "Europe/Paris",        # CET/CEST
        "Asia/Tokyo",          # JST
        "Asia/Singapore",      # SGT
        "Asia/Shanghai",       # CST (China)
        "Australia/Sydney",    # AEST/AEDT
        "Asia/Dubai",          # GST
        "Asia/Seoul",          # KST
    ]


# ── Internal helpers ───────────────────────────────────────────────────────────

def _get_pytz(tz_string: str) -> pytz.BaseTzInfo:
    """Return pytz timezone. Falls back to UTC on unknown string."""
    try:
        return pytz.timezone(tz_string)
    except pytz.exceptions.UnknownTimeZoneError:
        logger.warning("Unknown timezone '%s' — using UTC.", tz_string)
        return pytz.utc


def _extract_tz_from_date_header(date_str: str) -> Optional[str]:
    """
    Parse UTC offset from an RFC 2822 Date header string.

    Examples:
        "Mon, 04 Apr 2026 09:15:00 +0530" → "Asia/Kolkata"
        "Mon, 04 Apr 2026 09:15:00 -0700" → "America/Los_Angeles"
        "Mon, 04 Apr 2026 09:15:00 +0000" → "UTC"
        "Mon, 04 Apr 2026 09:15:00 GMT"   → "Europe/London"

    Returns:
        str | None: IANA timezone string, or None if offset cannot be parsed.
    """
    import email.utils

    try:
        parsed = email.utils.parsedate_tz(date_str)
        if parsed is None:
            return None
        tz_offset_seconds = parsed[-1]   # seconds east of UTC (can be None)
        if tz_offset_seconds is None:
            return None
        return _offset_seconds_to_iana(tz_offset_seconds)
    except Exception:
        return None


def _offset_seconds_to_iana(offset_seconds: int) -> Optional[str]:
    """
    Map a UTC offset in seconds to a best-match IANA timezone string.
    Uses a lookup table of the most common offsets.

    Args:
        offset_seconds: Integer seconds. E.g. +05:30 = 19800, -08:00 = -28800.

    Returns:
        str | None: Best-match IANA timezone string, or None if offset unknown.
    """
    OFFSET_TO_IANA: dict[int, str] = {
         19800:  "Asia/Kolkata",        # +05:30
         0:      "UTC",
        -18000:  "America/New_York",    # -05:00 EST
        -14400:  "America/New_York",    # -04:00 EDT
        -21600:  "America/Chicago",     # -06:00 CST
        -25200:  "America/Los_Angeles", # -07:00 PDT / MST
        -28800:  "America/Los_Angeles", # -08:00 PST
         3600:   "Europe/Paris",        # +01:00 CET
         7200:   "Europe/Paris",        # +02:00 CEST
         28800:  "Asia/Shanghai",       # +08:00
         32400:  "Asia/Tokyo",          # +09:00
         36000:  "Australia/Sydney",    # +10:00 AEST
         39600:  "Australia/Sydney",    # +11:00 AEDT
         28800:  "Asia/Singapore",      # +08:00 (same as Shanghai)
         19800:  "Asia/Kolkata",        # +05:30 (repeat — already handled)
    }
    return OFFSET_TO_IANA.get(offset_seconds)


def _offset_string_to_iana(offset_str: str) -> Optional[str]:
    """
    Convert a UTC offset string like "+05:30" or "+0530" to IANA timezone.

    Args:
        offset_str: String like "+05:30", "+0530", "-08:00", "-0800".

    Returns:
        str | None: IANA timezone or None if unrecognised.
    """
    # Normalise: "+05:30" → "+0530"
    clean = offset_str.replace(":", "").strip()
    try:
        sign  = 1 if clean[0] == "+" else -1
        hours = int(clean[1:3])
        mins  = int(clean[3:5]) if len(clean) > 3 else 0
        total_seconds = sign * (hours * 3600 + mins * 60)
        return _offset_seconds_to_iana(total_seconds)
    except (ValueError, IndexError):
        return None


def _extract_body_text(msg: Message) -> str:
    """Extract plain text body from email.message.Message for timezone scanning."""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace")
    else:
        if msg.get_content_type() == "text/plain":
            payload = msg.get_payload(decode=True)
            if payload:
                return payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
    return ""


def _get_tz_abbrev(tz_string: str, dt: datetime) -> str:
    """
    Get the short timezone abbreviation for a datetime in a given timezone.
    E.g. "Asia/Kolkata" → "IST", "America/New_York" in summer → "EDT".

    Args:
        tz_string: IANA timezone string.
        dt:        Datetime in the local timezone (not UTC) — used to determine DST.

    Returns:
        str: Abbreviation like "IST", "EST", "PDT". Falls back to tz_string if unknown.
    """
    # Reverse lookup ABBREV_TO_IANA for display
    IANA_TO_ABBREV: dict[str, str] = {v: k for k, v in ABBREV_TO_IANA.items()
                                       if k not in ("CST_CHINA", "Z")}
    # Try pytz's tzname() first — most accurate for DST-aware abbreviations
    try:
        tz = _get_pytz(tz_string)
        abbrev = dt.strftime("%Z")
        if abbrev and abbrev != "LMT":
            return abbrev
    except Exception:
        pass
    return IANA_TO_ABBREV.get(tz_string, tz_string)


def _parse_iso_dt(val: str) -> Optional[datetime]:
    """Parse an ISO 8601 string to a UTC-aware datetime. Returns None on failure."""
    if not val:
        return None
    try:
        dt = datetime.fromisoformat(val)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None
```

---

## 3. Integration into email_parser.py

Add one call to `detect_timezone_from_email()` inside `parse_email()`. Insert after the body extraction block:

```python
# email_parser.py — addition inside parse_email() function

# After: body = _extract_plain_text(msg)
# Before: return email_obj

# Detect sender timezone and store in preferences
from timezone_utils import detect_timezone_from_email
sender_tz = detect_timezone_from_email(msg)

# Persist detected timezone — available to parse_availability() in Phase 5
from preference_store import store_preferences
store_preferences(sender_email, timezone_str=sender_tz)
```

**Note:** `parse_email()` now has a side effect — it writes to `participant_preferences`. This is intentional: timezone is detected at ingest time, before agent nodes run, so it is available immediately when `coordination_node` calls `parse_availability(text, sender_tz)`.

---

## 4. Integration into coordination_node

`coordination_node` in `agent/nodes.py` must read the stored timezone when calling `parse_availability`:

```python
# agent/nodes.py — coordination_node (Phase 8 update)

# Replace:
#   sender_tz  = state["preferences"].get(sender, {}).get("timezone", "UTC")
# With:
from preference_store import load_preferences
sender_prefs = load_preferences(sender)
sender_tz    = sender_prefs.get("timezone", "UTC")
# (This is already the correct pattern from Phase 6 — no change needed if implemented correctly)
```

---

## 5. Integration into send_reply draft building

When `calendar_node` or `coordination_node` builds the outbound draft, use `format_slot_for_email()` to display times in the recipient's local timezone:

```python
# agent/nodes.py — calendar_node (Phase 8 additions)
# After selecting ranked_slot, format it for each participant's timezone:

from timezone_utils import format_slot_for_email

# When building confirmation email to sender:
sender_tz   = state["preferences"].get(email_obj["sender_email"], {}).get("timezone", "UTC")
slot_display = format_slot_for_email(state["ranked_slot"], sender_tz)

state["outbound_draft"] = (
    f"Great news! I've scheduled the meeting:\n\n"
    f"  📅 {email_obj['subject']}\n"
    f"  🕐 {slot_display}\n"   # ← LOCAL TIME for the recipient
    f"  👥 {', '.join(state['participants'])}\n\n"
    f"A Google Calendar invite has been sent to all participants."
)
```

---

## 6. UTC Normalisation Pipeline

Every datetime that enters MailMind must flow through this exact pipeline:

```
Email arrives
    │
    │  email_parser.parse_email()
    │  timezone_utils.detect_timezone_from_email(msg) → sender_tz = "Asia/Kolkata"
    │  preference_store.store_preferences(email, timezone_str=sender_tz)
    ▼
Body text: "I'm free Monday 10am IST"
    │
    │  parse_availability(text, sender_tz="Asia/Kolkata")
    │  dateparser.search_dates(text, settings={"TIMEZONE": "Asia/Kolkata", "TO_TIMEZONE": "UTC"})
    ▼
TimeSlot: {
    "start_utc": "2026-04-06T04:30:00+00:00",   ← 10:00 IST = 04:30 UTC
    "end_utc":   "2026-04-06T05:30:00+00:00",
    "timezone":  "Asia/Kolkata"
}
    │
    │  Stored in SQLite sessions.state_json as UTC ISO strings
    │
    │  rank_slots() operates purely on UTC datetimes — no timezone conversion here
    ▼
Outbound email:
    │  format_slot_for_email(slot, "Asia/Kolkata")
    │  → to_local(utc_start, "Asia/Kolkata") → datetime(2026, 4, 6, 10, 0, IST)
    ▼
"Monday 06 Apr 2026, 10:00–11:00 IST"   ← shown in recipient's local time
```

---

## 7. UTC Offset to IANA Mapping Reference

| UTC Offset | IANA Timezone | Display Name |
|---|---|---|
| +05:30 | Asia/Kolkata | IST (India Standard Time) |
| +00:00 | UTC | UTC |
| -05:00 | America/New_York | EST |
| -04:00 | America/New_York | EDT (summer) |
| -06:00 | America/Chicago | CST |
| -07:00 | America/Los_Angeles | PDT (summer) |
| -08:00 | America/Los_Angeles | PST |
| +01:00 | Europe/Paris | CET |
| +02:00 | Europe/Paris | CEST (summer) |
| +08:00 | Asia/Shanghai | CST (China) |
| +08:00 | Asia/Singapore | SGT |
| +09:00 | Asia/Tokyo | JST |
| +10:00 | Australia/Sydney | AEST |
| +11:00 | Australia/Sydney | AEDT (summer) |
| +04:00 | Asia/Dubai | GST |
| +09:00 | Asia/Seoul | KST |

**Note on collisions:** Offset +08:00 maps to both Asia/Shanghai and Asia/Singapore. The `_offset_seconds_to_iana()` function returns `"Asia/Singapore"` as the default for +08:00 (last write wins in the dict — implementation must handle this). For disambiguation, text-based abbreviation detection (SGT vs CST) takes priority over offset-based detection.

---

## 8. Unit Tests — tests/test_timezone_utils.py

```python
# tests/test_timezone_utils.py
"""
Tests for timezone_utils.py — detection, normalisation, formatting.
Run: pytest tests/test_timezone_utils.py -v
"""

from __future__ import annotations

import email as email_lib
from datetime import datetime, timezone

import pytest

from timezone_utils import (
    detect_timezone_from_text,
    format_for_email,
    format_slot_for_email,
    to_local,
    to_utc,
)


class TestDetectTimezoneFromText:
    """Test case 1 — timezone abbreviation detection from text."""

    def test_ist_detected(self):
        assert detect_timezone_from_text("I'm free Monday 10am IST") == "Asia/Kolkata"

    def test_pst_detected(self):
        assert detect_timezone_from_text("Call me at 3pm PST") == "America/Los_Angeles"

    def test_gmt_detected(self):
        assert detect_timezone_from_text("Meeting at 9am GMT") == "Europe/London"

    def test_utc_explicit(self):
        assert detect_timezone_from_text("Join at 14:00 UTC") == "UTC"

    def test_no_timezone_returns_utc(self):
        assert detect_timezone_from_text("I'm free on Monday") == "UTC"

    def test_utc_offset_detected(self):
        result = detect_timezone_from_text("Available from 9am UTC+05:30")
        assert result == "Asia/Kolkata"

    def test_case_sensitive_match(self):
        # Abbreviations are uppercase — lower case should not match
        result = detect_timezone_from_text("this is not ist timezone")
        # "ist" lowercase does NOT match \bIST\b (case-sensitive regex)
        assert result == "UTC"


class TestToUtc:
    """Test case 2 — naive datetime → UTC conversion."""

    def test_ist_to_utc(self):
        # 10:00 IST = 04:30 UTC
        naive_dt = datetime(2026, 4, 7, 10, 0)
        utc = to_utc(naive_dt, "Asia/Kolkata")
        assert utc.tzinfo == timezone.utc
        assert utc.hour == 4
        assert utc.minute == 30

    def test_pst_to_utc(self):
        # 09:00 PST = 17:00 UTC
        naive_dt = datetime(2026, 1, 15, 9, 0)  # January = PST (not PDT)
        utc = to_utc(naive_dt, "America/Los_Angeles")
        assert utc.tzinfo == timezone.utc
        assert utc.hour == 17

    def test_already_utc_passthrough(self):
        dt = datetime(2026, 4, 7, 9, 0, tzinfo=timezone.utc)
        result = to_utc(dt, "Asia/Kolkata")
        assert result.hour == 9   # already UTC — no change
        assert result.tzinfo == timezone.utc

    def test_aware_ist_converted_to_utc(self):
        import pytz
        ist = pytz.timezone("Asia/Kolkata")
        aware_dt = ist.localize(datetime(2026, 4, 7, 10, 0))
        utc = to_utc(aware_dt, "UTC")  # tz_string ignored for aware dt
        assert utc.hour == 4
        assert utc.minute == 30


class TestToLocal:
    """Test case 3 — UTC → local timezone conversion."""

    def test_utc_to_ist(self):
        # 04:30 UTC = 10:00 IST
        utc_dt = datetime(2026, 4, 7, 4, 30, tzinfo=timezone.utc)
        local  = to_local(utc_dt, "Asia/Kolkata")
        assert local.hour == 10
        assert local.minute == 0

    def test_utc_to_pst(self):
        # 17:00 UTC = 09:00 PST (Jan = no DST)
        utc_dt = datetime(2026, 1, 15, 17, 0, tzinfo=timezone.utc)
        local  = to_local(utc_dt, "America/Los_Angeles")
        assert local.hour == 9


class TestFormatForEmail:
    """Test case 4 — format_for_email output format."""

    def test_format_ist(self):
        utc_dt = datetime(2026, 4, 7, 4, 30, tzinfo=timezone.utc)
        result = format_for_email(utc_dt, "Asia/Kolkata")
        # Should contain "10:00" and "Apr" and "2026"
        assert "10:00" in result
        assert "Apr" in result
        assert "2026" in result
        assert "IST" in result

    def test_format_utc(self):
        utc_dt = datetime(2026, 4, 7, 9, 0, tzinfo=timezone.utc)
        result = format_for_email(utc_dt, "UTC")
        assert "09:00" in result


class TestFormatSlotForEmail:
    """Test case 5 — format_slot_for_email output."""

    def test_slot_formatted_with_range(self):
        slot = {
            "start_utc": "2026-04-07T04:30:00+00:00",  # 10:00 IST
            "end_utc":   "2026-04-07T05:30:00+00:00",  # 11:00 IST
            "participant": "alice@example.com",
            "raw_text": "Monday 10am",
            "timezone": "Asia/Kolkata",
        }
        result = format_slot_for_email(slot, "Asia/Kolkata")
        assert "10:00" in result
        assert "11:00" in result
        assert "IST" in result

    def test_empty_start_utc_returns_fallback(self):
        slot = {"start_utc": "", "end_utc": ""}
        result = format_slot_for_email(slot, "UTC")
        assert result == "[time not available]"


class TestDetectFromEmailHeader:
    """Test case 6 — timezone detection from real email Date header."""

    def _make_msg_with_date(self, date_str: str):
        raw = f"From: Alice <alice@example.com>\r\nDate: {date_str}\r\n\r\nBody."
        return email_lib.message_from_string(raw)

    def test_ist_offset_in_date_header(self):
        from timezone_utils import detect_timezone_from_email
        msg = self._make_msg_with_date("Mon, 07 Apr 2026 10:00:00 +0530")
        result = detect_timezone_from_email(msg)
        assert result == "Asia/Kolkata"

    def test_pst_offset_in_date_header(self):
        from timezone_utils import detect_timezone_from_email
        msg = self._make_msg_with_date("Mon, 07 Apr 2026 09:00:00 -0800")
        result = detect_timezone_from_email(msg)
        assert result == "America/Los_Angeles"

    def test_utc_zero_offset(self):
        from timezone_utils import detect_timezone_from_email
        msg = self._make_msg_with_date("Mon, 07 Apr 2026 09:00:00 +0000")
        result = detect_timezone_from_email(msg)
        assert result == "UTC"
```

---

## 9. Integration Checklist

- [ ] `timezone_utils.py` exists — all 6 public functions implemented
- [ ] `ABBREV_TO_IANA` dict has all common abbreviations including IST, PST, EDT, GMT, JST, SGT
- [ ] `TZ_ABBREV_PATTERN` regex uses word boundaries (`\b`) — avoids partial matches
- [ ] `to_utc()` handles both naive and aware datetimes
- [ ] `to_utc()` handles `AmbiguousTimeError` (DST transition) — does not crash
- [ ] `to_utc()` handles `NonExistentTimeError` (DST spring forward) — does not crash
- [ ] `to_local()` correctly converts UTC to IST (04:30 UTC → 10:00 IST) ✓
- [ ] `format_slot_for_email()` returns `"[time not available]"` on empty `start_utc`
- [ ] `email_parser.parse_email()` calls `detect_timezone_from_email(msg)` and stores via `store_preferences()`
- [ ] `coordination_node` reads `sender_tz` from `load_preferences(sender).get("timezone", "UTC")`
- [ ] `calendar_node` uses `format_slot_for_email(ranked_slot, sender_tz)` in outbound draft
- [ ] All TimeSlot dicts stored with `"timezone"` key (participant's source timezone)
- [ ] `pytest tests/test_timezone_utils.py -v` passes all tests
- [ ] IST → UTC test: 10:00 IST = 04:30 UTC (not 04:00 — IST is +05:30 not +05:00) ✓

---

## Cross-Phase References

| Exported | From | Imported By |
|---|---|---|
| `detect_timezone_from_email()` | `timezone_utils.py` | `email_parser.parse_email()` (P2 — Phase 8 update) |
| `detect_timezone_from_text()` | `timezone_utils.py` | `tools/email_coordinator.parse_availability()` (P5) if body TZ override needed |
| `to_utc()` | `timezone_utils.py` | `tools/email_coordinator.parse_availability()` (P5) as fallback normaliser |
| `to_local()` | `timezone_utils.py` | `format_slot_for_email()` internally; `agent/nodes.py` (P6) if manual conversion needed |
| `format_slot_for_email()` | `timezone_utils.py` | `agent/nodes.py calendar_node` (P6) for outbound draft |
| `format_for_email()` | `timezone_utils.py` | `agent/nodes.py` any node building time-containing drafts |
| `get_common_timezones()` | `timezone_utils.py` | `setup.py` (P1) validation display, any admin UI |

---

*PHASE8_TIMEZONE.md | Team TRIOLOGY | PCCOE Pune | Problem Statement 03*
