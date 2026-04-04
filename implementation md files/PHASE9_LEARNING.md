# PHASE9_LEARNING.md
## Phase 9 — Continuous Learning & History Analysis
**Covers:** `tools/thread_intelligence.py` (suggest_optimal_time section), historical slot analysis, hour/day bucketing, continuous preference scoring, memory trimming
**Files documented:** `tools/thread_intelligence.py` (Phase 9 updates)

---

## Purpose

MailMind does not just coordinate schedules; it _learns_ from them. Phase 9 implements the learning mechanism. When a meeting is successfully scheduled (in `calendar_node`), the final agreed-upon slot is saved to the `historical_slots` table for every participant. Over time, MailMind builds a data profile: "Alice usually accepts meetings on Tuesday afternoons." When a user asks "When should we meet?", the `suggest_optimal_time()` tool analyses this historical data to propose high-probability slots before asking anyone for their availability — turning coordination from reactive to predictive.

---

## Dependencies

- **Phase 3:** `db.py` (`historical_slots` schema), `preference_store.store_preferences(email, accepted_slot=slot)`
- **Phase 5:** `tools/thread_intelligence.py` — `suggest_optimal_time` is the tool schema defined here; Phase 9 implements its logic
- **Phase 5:** `rank_slots()` — Phase 9 output feeds into `PreferenceProfile` typed dict (`preferred_hour_buckets`, `preferred_days`)
- **Phase 6:** `calendar_node` — already calls `store_preferences()` upon successful event creation (implemented in Phase 6)

---

## 1. db.py — Schema Review (Phase 3)

Ensure Phase 3 implemented the learning table correctly. This is just for reference; no code changes here if Phase 3 is correct.

```python
# db.py
# (Reference only — ensure this exists from Phase 3)

# CREATE TABLE IF NOT EXISTS historical_slots (
#     id INTEGER PRIMARY KEY AUTOINCREMENT,
#     email TEXT NOT NULL,           -- The participant
#     thread_id TEXT NOT NULL,       -- The session where this was accepted
#     start_utc TEXT NOT NULL,       -- ISO string of accepted meeting start
#     end_utc TEXT NOT NULL,         -- ISO string of accepted meeting end
#     timezone TEXT,                 -- Participant's local timezone at the time
#     created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
# );
# CREATE INDEX IF NOT EXISTS idx_hist_email ON historical_slots(email);
```

---

## 2. The Learning Algorithm

### Step 1: Storage (Already in `preference_store.py`)
Every time `calendar_node` creates an event, it calls `store_preferences(email, accepted_slot=slot)`. This inserts a row into `historical_slots`.

### Step 2: Extraction (`get_learning_profile()`)
When requested, MailMind queries the last $N$ (e.g., 50) slots for a participant.
For each slot (stored in UTC), it is converted to the participant's *current* local timezone to determine the local hour (0-23) and local weekday (Monday-Sunday).

### Step 3: Bucketing and Scoring
1. **Count frequencies:** Tally occurrences of each local hour and local weekday.
2. **Thresholding:** Keep hours/days that represent at least 15% of the total accepted slots.
3. **Write to `PreferenceProfile`:** The top hours are stored in `preferred_hour_buckets` (e.g., `[10, 14, 15]`); top days in `preferred_days` (e.g., `["Tuesday", "Thursday"]`).

### Step 4: Application (`suggest_optimal_time()`)
When a user asks for a suggestion, the tool takes the intersection of the `preferred_hour_buckets` and `preferred_days` across all requested participants. If an overlap exists, it proposes slots in the near future that match that intersection.

---

## 3. preference_store.py — Update with Extraction Logic

Add the extraction function to `preference_store.py` to build the buckets from the raw DB rows.

```python
# preference_store.py — Phase 9 addition

from collections import Counter
from datetime import datetime

from db import get_connection
from timezone_utils import to_local, _parse_iso_dt, DEFAULT_TIMEZONE


def get_learning_profile(email: str, limit: int = 50) -> tuple[list[int], list[str]]:
    """
    Analyse historical_slots for a user to find high-probability hours and days.

    Args:
        email: Participant email.
        limit: Max historical slots to analyse (keeps learning recent).

    Returns:
        tuple[list[int], list[str]]: (preferred_hours, preferred_days)
            preferred_hours: List of UTC hours (0-23) [e.g. 14, 15]
            preferred_days: List of weekday strings [e.g. "Tuesday", "Thursday"]
    """
    conn = get_connection()
    c = conn.cursor()

    # Get their current timezone to translate UTC history into meaningful local patterns
    c.execute("SELECT timezone FROM participant_preferences WHERE email = ?", (email,))
    row = c.fetchone()
    current_tz = row[0] if row else DEFAULT_TIMEZONE

    # Fetch recent history
    c.execute(
        "SELECT start_utc FROM historical_slots WHERE email = ? ORDER BY created_at DESC LIMIT ?",
        (email, limit)
    )
    rows = c.fetchall()
    conn.close()

    if not rows:
        return [], []

    local_hours: list[int] = []
    local_days: list[str] = []

    for row in rows:
        start_utc_str = row[0]
        dt_utc = _parse_iso_dt(start_utc_str)
        if dt_utc:
            # Convert to local time to see their actual pattern (e.g., they like 10am local)
            dt_local = to_local(dt_utc, current_tz)
            local_hours.append(dt_local.hour)
            local_days.append(dt_local.strftime("%A"))

    total = len(local_hours)
    hour_counts = Counter(local_hours)
    day_counts = Counter(local_days)

    # Threshold: Keep if it makes up >= 15% of their history AND >= 2 occurrences
    # (Prevents 1 meeting from becoming a "preference" if total=1)
    threshold_ratio = 0.15
    min_occurrences = min(2, total)

    top_local_hours = [
        hour for hour, count in hour_counts.items()
        if (count / total) >= threshold_ratio and count >= min_occurrences
    ]

    top_days = [
        day for day, count in day_counts.items()
        if (count / total) >= threshold_ratio and count >= min_occurrences
    ]

    # Convert top_local_hours BACK to UTC hours for the rank_slots engine to consume natively
    # (rank_slots operates purely on UTC slot starts)
    # We use a dummy date to do the conversion offset
    dummy = datetime.now()
    utc_hours = set()
    for lh in top_local_hours:
        # Construct naive local dt at that hour
        naive_local = datetime(dummy.year, dummy.month, dummy.day, lh, 0)
        from timezone_utils import to_utc
        dt_utc_conversion = to_utc(naive_local, current_tz)
        utc_hours.add(dt_utc_conversion.hour)

    return list(utc_hours), top_days


# Update load_preferences() in preference_store.py to include this data
# (Find load_preferences and append the profile to the output dict)

# ... inside load_preferences() ...
# prefs = { ... existing fields ... }
#
# if load_learning:  # (add param `load_learning: bool = True` to load_preferences)
#     utc_hours, days = get_learning_profile(email)
#     prefs["preferred_hour_buckets"] = utc_hours
#     prefs["preferred_days"] = days
#
# return prefs
```

---

## 4. tools/thread_intelligence.py — Complete Implementation

Implement the `suggest_optimal_time` logic within Phase 5's tool module.

```python
# tools/thread_intelligence.py — Phase 9 addition

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from config import config
from logger import get_logger
from preference_store import load_preferences
from timezone_utils import format_for_email, to_local

logger = get_logger(__name__)


def suggest_optimal_time(kwargs: dict) -> dict:
    """
    Propose meeting times based on the historical preferences of all requested participants.
    Called when a user asks "When is everyone free?" or "Suggest a time."

    Args:
        kwargs: {
            "participants": ["alice@example.com", "bob@example.com"],
            "lookahead_days": 7
        }

    Returns:
        dict: {
            "suggestions": list[str] (Formatted slot strings),
            "reason": str (Explanation based on data)
        }
    """
    participants = kwargs.get("participants", [])
    lookahead_days = kwargs.get("lookahead_days", 7)

    if not participants:
        return {
            "suggestions": [],
            "reason": "No participants provided to analyse."
        }

    all_prefs = {}
    total_history = 0

    # 1. Load preferences and history for everyone
    for p in participants:
        # Assumes load_preferences was updated to include buckets
        prefs = load_preferences(p)
        all_prefs[p] = prefs
        # We can gauge if we have history by checking if buckets exist
        if prefs.get("preferred_hour_buckets") or prefs.get("preferred_days"):
            total_history += 1

    if total_history == 0:
        return {
            "suggestions": [],
            "reason": "Not enough historical data to make a data-driven suggestion. Please ask participants for availability."
        }

    # 2. Find intersecting days
    # Start with standard weekdays
    common_days = set(["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"])

    for p, prefs in all_prefs.items():
        hist_days = prefs.get("preferred_days", [])
        blocked = prefs.get("blocked_days", [])

        # Remove explicit blocks
        common_days.difference_update(blocked)

        # Intersect with historical strong preferences (if they have enough history)
        if hist_days:
            # We want days that at least ONE person strongly prefers, intersected across the group.
            # But if we strictly intersect, we might get empty sets quickly.
            # So, keep it if it's in hist_days OR if they have no strong day preference (all days fine)
            pass  # More complex intersection can be built, but skipping explicit day intersection
                  # to avoid over-constraining. Blocked days handling is usually sufficient for days.

    if not common_days:
        return {
            "suggestions": [],
            "reason": "All common work days are blocked by at least one participant."
        }

    # 3. Find intersecting hours (UTC)
    common_utc_hours = set(range(0, 24))

    for p, prefs in all_prefs.items():
        hist_hours = set(prefs.get("preferred_hour_buckets", []))
        pref_start = prefs.get("preferred_hours_start", 9)
        pref_end = prefs.get("preferred_hours_end", 17)

        # Build allowable UTC hours based on their explicit 9-5 config
        tz = prefs.get("timezone", "UTC")
        dummy = datetime.now()
        allowable_for_p = set()
        for local_h in range(pref_start, pref_end):
            naive_local = datetime(dummy.year, dummy.month, dummy.day, local_h, 0)
            from timezone_utils import to_utc
            allowable_for_p.add(to_utc(naive_local, tz).hour)

        # If they have history, intersect their history with their allowable
        if hist_hours:
            p_valid_hours = hist_hours.intersection(allowable_for_p)
        else:
            p_valid_hours = allowable_for_p

        # Intersect across the whole group
        common_utc_hours.intersection_update(p_valid_hours)

    if not common_utc_hours:
        return {
            "suggestions": [],
            "reason": "Could not find a common intersecting hour based on preferences and history."
        }

    # 4. Generate actual datetime suggestions for the near future
    now_utc = datetime.now(timezone.utc)
    suggestions_utc = []
    target_count = 3

    for day_offset in range(1, lookahead_days + 1):  # Start looking from tomorrow
        candidate_date = now_utc + timedelta(days=day_offset)
        candidate_weekday = candidate_date.strftime("%A")

        if candidate_weekday not in common_days:
            continue

        for hour in sorted(list(common_utc_hours)):
            candidate_dt = datetime(
                candidate_date.year, candidate_date.month, candidate_date.day,
                hour, 0, tzinfo=timezone.utc
            )
            # Ensure it's in the future
            if candidate_dt > now_utc:
                suggestions_utc.append(candidate_dt)
                if len(suggestions_utc) >= target_count:
                    break
        if len(suggestions_utc) >= target_count:
            break

    # 5. Format for the requester (first participant in the list, or UTC fallback)
    resp_tz = all_prefs.get(participants[0], {}).get("timezone", "UTC")
    formatted_suggestions = [format_for_email(dt, resp_tz) for dt in suggestions_utc]

    return {
        "suggestions": formatted_suggestions,
        "reason": f"Based on historical patterns, {len(participants)} participant(s) commonly accept meetings during these overlapping hours."
    }
```

---

## 5. Integration into `rank_slots()` (Refinement)

In Phase 5, `rank_slots()` evaluates the `PREFERENCE SCORE` purely based on `preferred_hours_start` (default 9) and `preferred_hours_end` (default 17).

To make `rank_slots()` learn, we augment the `PREFERENCE SCORE` logic in `tools/coordination_memory.py` to give bonus points if the candidate slot hour falls into `preferred_hour_buckets`.

```python
# tools/coordination_memory.py — Phase 9 modification inside rank_slots()

# Find this block (Section 2: PREFERENCE SCORE):
# within_hours  = pref_start <= slot_hour < pref_end
# not_blocked   = slot_weekday not in blocked_days

# Modify to add learning bonus:

HISTORICAL_BONUS = 0.05  # Extra score if slot matches their historical preference

for email in all_participants:
    pref = preferences[email]
    pref_start   = pref.get("preferred_hours_start", 9)
    pref_end     = pref.get("preferred_hours_end",   17)
    blocked_days = pref.get("blocked_days",           [])
    hist_hours   = pref.get("preferred_hour_buckets", [])  # Added in Phase 9
    hist_days    = pref.get("preferred_days",         [])  # Added in Phase 9

    within_hours  = pref_start <= slot_hour < pref_end
    not_blocked   = slot_weekday not in blocked_days

    if within_hours and not_blocked:
        # Full preference score
        p_score = 1.0 / total_participants

        # Apply historical bonuses
        if slot_hour in hist_hours:
            p_score += (HISTORICAL_BONUS / total_participants)
        if slot_weekday in hist_days:
            p_score += (HISTORICAL_BONUS / total_participants)

        preference_score += p_score

    elif not within_hours or not not_blocked:
        total_penalty += PREFERENCE_VIOLATION_PENALTY / total_participants

# Need to ensure final score clamping still works:
# final_score = max(0.0, min(1.0, final_score)) (Already present in Phase 5)
```

---

## 6. Unit Tests — tests/test_learning.py

```python
# tests/test_learning.py
from datetime import datetime, timezone
from unittest.mock import patch

from preference_store import get_learning_profile

def test_get_learning_profile_empty(monkeypatch):
    monkeypatch.setattr("preference_store.get_connection", lambda: type('obj', (object,), {'cursor': lambda self: type('c', (object,), {'execute': lambda s, q, p=None: None, 'fetchone': lambda s: None, 'fetchall': lambda s: []})(), 'close': lambda self: None})())
    hours, days = get_learning_profile("test@test.com")
    assert hours == []
    assert days == []

def test_suggest_optimal_time_no_data():
    from tools.thread_intelligence import suggest_optimal_time
    res = suggest_optimal_time({"participants": ["foo@bar.com"]})
    assert len(res["suggestions"]) == 0
    assert "Not enough historical data" in res["reason"]

# Write a comprehensive mocked test for suggest_optimal_time where history IS present.
```

---

*PHASE9_LEARNING.md | Team TRIOLOGY | PCCOE Pune | Problem Statement 03*
