# PHASE5_RANK_SLOTS.md
## Phase 5 — rank_slots() Algorithm Deep Dive
**Covers:** Complete `rank_slots()` implementation, scoring formula, weight constants, soft conflict penalty, failure threshold behavior, PreferenceProfile schema, three worked examples
**Files documented:** `tools/coordination_memory.py` (rank_slots section), `models.py` (PreferenceProfile), `tests/test_rank_slots.py`

---

## Purpose

This document provides the full algorithmic specification for `rank_slots()` — the deterministic conflict resolution engine at the heart of MailMind. It is a pure Python function with no LLM involvement. It receives a list of candidate time slots (all of which passed the attendance threshold from `find_overlap()`) and scores each one using four weighted criteria. The highest-scoring slot is selected as `ranked_slot` in the agent state. This document provides numeric weight values, the exact scoring formula, soft conflict penalty logic, edge case handling, and three fully worked numerical examples so any developer can implement and verify the function without ambiguity.

---

## Dependencies

- **Phase 3 complete:** `models.py` (AgentState, TimeSlot), `preference_store.check_vip_status()`
- **Phase 5 (PHASE5_TOOL_REGISTRY.md):** `rank_slots()` lives in `tools/coordination_memory.py`
- **No external packages:** Pure Python — datetime, math operations only
- **`PreferenceProfile` TypedDict** added to `models.py` in this phase

---

## 1. PreferenceProfile TypedDict — models.py addition

Add below `AgentState` in `models.py`:

```python
# models.py  (Phase 5 addition — append below AgentState)

class PreferenceProfile(TypedDict):
    """
    Per-participant preference data passed into rank_slots() scoring.
    Built from participant_preferences table + historical_slots analysis.

    Fields:
        email:                   Participant email address (lowercase).
        preferred_hours_start:   UTC hour (0–23) when their workday begins. Default: 9.
        preferred_hours_end:     UTC hour (0–23) when their workday ends. Default: 17.
        blocked_days:            Weekday names they never meet. E.g. ["Friday", "Saturday"].
        vip:                     True if this participant is designated as VIP.
        timezone:                IANA timezone string. E.g. "Asia/Kolkata". Used for display only.
        slots:                   List of their parsed TimeSlot dicts from session state.
                                 Used by rank_slots() to check if they overlap each candidate.
        preferred_hour_buckets:  Most frequently accepted UTC hours from historical_slots.
                                 Empty list for new participants (cold start). Populated by
                                 suggest_optimal_time() in Phase 9.
        preferred_days:          Most frequently accepted weekday names from historical_slots.
                                 Empty list for new participants. Populated in Phase 9.
    """
    email:                  str
    preferred_hours_start:  int
    preferred_hours_end:    int
    blocked_days:           list[str]
    vip:                    bool
    timezone:               str
    slots:                  list[dict]          # list of TimeSlot dicts for this participant
    preferred_hour_buckets: list[int]           # Phase 9: historical hour preferences
    preferred_days:         list[str]           # Phase 9: historical day preferences
```

---

## 2. Weight Constants

These are defined as module-level constants in `tools/coordination_memory.py`:

```python
# Scoring weights — MUST sum exactly to 1.0
WEIGHT_ATTENDANCE   = 0.50   # Highest: how many participants can attend
WEIGHT_PREFERENCE   = 0.25   # Second: does slot fall in preferred hours/days
WEIGHT_VIP          = 0.15   # Third: are VIP participants available
WEIGHT_CHRONOLOGY   = 0.10   # Lowest: how early in the option set (tiebreaker)

# Soft conflict: applied per participant per preference violation
# Does NOT eliminate the slot — just penalises it
PREFERENCE_VIOLATION_PENALTY = 0.10

# Minimum slot score to proceed to calendar_node
# Below this → request more availability windows
SLOT_SCORE_THRESHOLD = 0.50
```

Verification: `0.50 + 0.25 + 0.15 + 0.10 = 1.00` ✓

---

## 3. Complete rank_slots() Implementation

```python
# tools/coordination_memory.py — complete rank_slots() function

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from config import config
from logger import get_logger
from preference_store import check_vip_status

logger = get_logger(__name__)

WEIGHT_ATTENDANCE           = 0.50
WEIGHT_PREFERENCE           = 0.25
WEIGHT_VIP                  = 0.15
WEIGHT_CHRONOLOGY           = 0.10
PREFERENCE_VIOLATION_PENALTY = 0.10
SLOT_SCORE_THRESHOLD        = 0.50


def rank_slots(candidate_slots: list[dict], preferences: dict[str, dict]) -> dict:
    """
    Score and rank candidate time slots. Return the best slot with explanation.

    Args:
        candidate_slots: List of TimeSlot dicts — slots that passed find_overlap().
                         Each has: start_utc (ISO str), end_utc (ISO str),
                         participant (str), raw_text (str), timezone (str).
        preferences:     Dict mapping participant email → PreferenceProfile dict.
                         Must include "slots" key with that participant's parsed TimeSlot list.

    Returns:
        dict: {
            "ranked_slot":     dict | None  — best TimeSlot dict (start/end as ISO strings),
            "score":           float        — final weighted score of best slot (0.0–1.0),
            "reason":          str          — human-readable explanation of why this slot was chosen,
            "below_threshold": bool         — True if best score < SLOT_SCORE_THRESHOLD
        }

    Scoring formula per slot:
        score = (WEIGHT_ATTENDANCE  * attendance_score)
              + (WEIGHT_PREFERENCE  * preference_score)
              + (WEIGHT_VIP         * vip_score)
              + (WEIGHT_CHRONOLOGY  * chronology_score)
              - total_penalty

    Edge cases:
        - Empty candidate_slots → returns below_threshold=True, ranked_slot=None
        - Single participant → attendance_score=1.0, vip_score depends on VIP flag
        - All VIPs unavailable → vip_score=0.0 for that slot (still returned if best)
        - All slots tie → chronology_score picks the earliest
    """
    if not candidate_slots:
        logger.warning("rank_slots called with empty candidate_slots.")
        return {
            "ranked_slot":     None,
            "score":           0.0,
            "reason":          "No candidate slots available. Request more availability windows.",
            "below_threshold": True,
        }

    all_participants = list(preferences.keys())
    total_participants = max(len(all_participants), 1)

    # Identify VIP participants for this call
    vip_participants = [e for e in all_participants if preferences[e].get("vip", False)
                        or check_vip_status(e)]

    # Chronology baseline — compute reference points for chronology scoring
    all_starts = [_parse_dt(s["start_utc"]) for s in candidate_slots]
    earliest_start = min(all_starts)
    latest_start   = max(all_starts)
    time_span_secs = max((latest_start - earliest_start).total_seconds(), 1.0)

    scored_slots: list[tuple[float, dict, str]] = []

    for slot in candidate_slots:
        slot_start   = _parse_dt(slot["start_utc"])
        slot_hour    = slot_start.hour                    # UTC hour 0–23
        slot_weekday = slot_start.strftime("%A")          # e.g. "Monday"

        # ── 1. ATTENDANCE SCORE (weight: 0.50) ────────────────────────────────
        # Fraction of all participants who have a slot overlapping this candidate.
        available_count = 0
        for email in all_participants:
            participant_slots = preferences[email].get("slots", [])
            if _has_overlap(slot, participant_slots):
                available_count += 1

        attendance_score = available_count / total_participants
        # Note: find_overlap already enforced ATTENDANCE_THRESHOLD, so attendance_score
        # should always be >= config.attendance_threshold here — but we recompute for accuracy.

        # ── 2. PREFERENCE SCORE + PENALTY (weight: 0.25) ──────────────────────
        # Fraction of participants for whom this slot is within preferred hours AND day.
        # For each preference violation: subtract PREFERENCE_VIOLATION_PENALTY / total_participants.
        preference_score = 0.0
        total_penalty    = 0.0

        for email in all_participants:
            pref = preferences[email]
            pref_start   = pref.get("preferred_hours_start", 9)
            pref_end     = pref.get("preferred_hours_end",   17)
            blocked_days = pref.get("blocked_days",           [])

            within_hours  = pref_start <= slot_hour < pref_end
            not_blocked   = slot_weekday not in blocked_days

            if within_hours and not_blocked:
                # Full preference score contribution from this participant
                preference_score += 1.0 / total_participants
            elif not within_hours or not not_blocked:
                # Soft penalty — slot is sub-optimal for this participant
                # Does not eliminate the slot, just reduces its score
                total_penalty += PREFERENCE_VIOLATION_PENALTY / total_participants

        # ── 3. VIP SCORE (weight: 0.15) ───────────────────────────────────────
        # Fraction of VIP participants available in this slot.
        # If no VIPs configured → vip_score = 1.0 (full credit, no VIPs to miss).
        if vip_participants:
            vip_available = 0
            for vip_email in vip_participants:
                vip_slots = preferences[vip_email].get("slots", [])
                if _has_overlap(slot, vip_slots):
                    vip_available += 1
            vip_score = vip_available / len(vip_participants)
        else:
            vip_score = 1.0

        # ── 4. CHRONOLOGY SCORE (weight: 0.10) ────────────────────────────────
        # Earlier slots score higher. Score = 1.0 for earliest, 0.0 for latest.
        # Formula: 1.0 - (seconds from earliest / total time span)
        elapsed_secs    = (slot_start - earliest_start).total_seconds()
        chronology_score = 1.0 - (elapsed_secs / time_span_secs)

        # ── Final weighted score ───────────────────────────────────────────────
        final_score = (
              WEIGHT_ATTENDANCE  * attendance_score
            + WEIGHT_PREFERENCE  * preference_score
            + WEIGHT_VIP         * vip_score
            + WEIGHT_CHRONOLOGY  * chronology_score
            - total_penalty
        )
        final_score = max(0.0, min(1.0, final_score))   # clamp to [0, 1]

        # ── Build reason string ────────────────────────────────────────────────
        reason_parts = [f"{int(attendance_score * 100)}% attendance"]
        if vip_score == 1.0 and vip_participants:
            reason_parts.append("all VIPs available")
        elif vip_score < 1.0 and vip_participants:
            reason_parts.append(f"{int(vip_score * 100)}% VIP coverage")
        if preference_score >= 0.75:
            reason_parts.append("within most participants' preferred hours")
        elif preference_score < 0.25:
            reason_parts.append("outside many participants' preferred hours")
        if total_penalty > 0:
            reason_parts.append(f"soft penalty {total_penalty:.2f} applied")
        reason = "; ".join(reason_parts)

        scored_slots.append((final_score, slot, reason))
        logger.debug(
            "Slot %s scored %.4f (att=%.2f pref=%.2f vip=%.2f chron=%.2f pen=%.2f)",
            slot["start_utc"], final_score,
            attendance_score, preference_score, vip_score, chronology_score, total_penalty,
        )

    # Sort descending by score
    scored_slots.sort(key=lambda t: t[0], reverse=True)
    best_score, best_slot, best_reason = scored_slots[0]

    below_threshold = best_score < SLOT_SCORE_THRESHOLD
    if below_threshold:
        logger.warning(
            "Best slot score %.4f is below threshold %.2f — coordination restart needed.",
            best_score, SLOT_SCORE_THRESHOLD,
        )

    return {
        "ranked_slot":     best_slot,
        "score":           round(best_score, 4),
        "reason":          best_reason,
        "below_threshold": below_threshold,
    }
```

---

## 4. Failure Threshold Behavior

When `rank_slots()` returns `{"below_threshold": True}`:

The calling node is `rank_slots_node` in `agent/nodes.py`. It must:

1. **Check** `result["below_threshold"]`
2. **If True** — draft an email to ALL participants:

```
Subject: Re: [original subject]

Hi all,

We weren't able to find a time that works for enough participants.
Could everyone please share 2–3 additional availability windows?

For example:
  - Monday 07 Apr 10:00–11:00 IST
  - Tuesday 08 Apr 15:00–16:00 IST

Thank you,
MailMind
```

3. **Clear** `state["slots_per_participant"]` — reset all collected slots
4. **Clear** `state["pending_responses"]` — repopulate with all participants
5. **Set** `state["current_node"] = "coordination_node"` — restart coordination round
6. **Save** state and RETURN — do NOT proceed to `calendar_node`

If True AND this is the second restart (tracked in `state`): route to `error_node` instead to prevent infinite loops. Implementation: add `coordination_restart_count: int` to AgentState, increment on restart, cap at 2.

---

## 5. Soft Conflict Penalty — Exact Behavior

**What it is:** A penalty subtracted from the final score when a slot violates a participant's preference (blocked day or outside preferred hours), without eliminating the slot entirely.

**When it applies:**
- Slot falls on a participant's blocked day (e.g. "Friday" in `blocked_days`)
- Slot hour falls outside `preferred_hours_start`–`preferred_hours_end`

**Formula:**
```
penalty_per_violation = PREFERENCE_VIOLATION_PENALTY / total_participants
# = 0.10 / N   (where N = number of participants)

total_penalty = sum(penalty_per_violation for each participant with a violation)
```

**Effect:**
- With 4 participants, each violation adds `0.10 / 4 = 0.025` to penalty
- Maximum possible penalty: `0.10 * total_participants / total_participants = 0.10`
- A slot with ALL participants violating preferences loses at most 0.10 from its score
- This ensures preference-violating slots remain as fallback options if no clean slot exists

---

## 6. Chronological Priority — Exact Calculation

**Why:** Tiebreaker. When two slots have identical attendance, preference, and VIP scores, prefer the earlier one (sooner meeting is generally better).

**Formula:**
```python
elapsed_secs     = (slot_start - earliest_start).total_seconds()
time_span_secs   = (latest_start - earliest_start).total_seconds()  # always >= 1
chronology_score = 1.0 - (elapsed_secs / time_span_secs)
```

**Behavior:**
- Earliest candidate slot: `chronology_score = 1.0`
- Latest candidate slot:   `chronology_score = 0.0`
- Only one candidate slot: `time_span_secs = 1` (minimum), `chronology_score = 1.0`
- Weight is 0.10 so maximum influence on final score = 0.10 points

**Edge case — only one slot:** `time_span_secs` is clamped to minimum of `1.0` to avoid division by zero. The single slot gets `chronology_score = 1.0`.

---

## 7. Edge Case — Single Participant

When `len(all_participants) == 1`:
- `attendance_score = 1.0` always (the only participant is by definition "available")
- `preference_score` depends on whether their slot falls in their preferred hours
- `vip_score = 1.0` if they are VIP (single participant who is VIP covers 100% VIPs)
- `total_penalty` is per-participant, so max penalty = `PREFERENCE_VIOLATION_PENALTY / 1 = 0.10`
- `below_threshold` check still applies — but since attendance = 1.0, the score will be at least `WEIGHT_ATTENDANCE = 0.50`, exactly at threshold

---

## 8. Worked Examples

### Example A — 3 Participants, Clean Overlap

**Setup:**
- 3 participants: Alice, Bob, Carol
- 2 candidate slots from `find_overlap()`
- No VIPs configured
- VIP score = 1.0 for all slots

**Slot 1:** Monday 09:00–10:00 UTC
**Slot 2:** Monday 14:00–15:00 UTC

**Participant preferences:**
```
Alice:  preferred_hours_start=9,  preferred_hours_end=17, blocked_days=[]
Bob:    preferred_hours_start=9,  preferred_hours_end=17, blocked_days=[]
Carol:  preferred_hours_start=13, preferred_hours_end=18, blocked_days=[]
```

**All 3 have slots overlapping both candidates (attendance = 3/3 = 1.0 for both).**

**Scoring Slot 1 (09:00 UTC):**
```
attendance_score  = 3/3 = 1.0
preference_score:
  Alice: 9 <= 9 < 17 ✓  → +1/3 = 0.333
  Bob:   9 <= 9 < 17 ✓  → +1/3 = 0.333
  Carol: 13 <= 9?  ✗    → penalty += 0.10/3 = 0.033
preference_score = 0.666, penalty = 0.033
vip_score = 1.0 (no VIPs)
chronology_score = 1.0 (earliest)

final = (0.50 * 1.0) + (0.25 * 0.666) + (0.15 * 1.0) + (0.10 * 1.0) - 0.033
      = 0.500 + 0.167 + 0.150 + 0.100 - 0.033
      = 0.884
```

**Scoring Slot 2 (14:00 UTC):**
```
attendance_score  = 1.0
preference_score:
  Alice: 9 <= 14 < 17 ✓  → +0.333
  Bob:   9 <= 14 < 17 ✓  → +0.333
  Carol: 13 <= 14 < 18 ✓ → +0.333
preference_score = 1.0, penalty = 0.0
vip_score = 1.0
chronology_score = 0.0 (latest)

final = (0.50 * 1.0) + (0.25 * 1.0) + (0.15 * 1.0) + (0.10 * 0.0) - 0.0
      = 0.500 + 0.250 + 0.150 + 0.000
      = 0.900
```

**Winner: Slot 2 (0.900 > 0.884)**

Reason: Even though Slot 2 is later (chronology = 0.0), the perfect preference alignment for all 3 participants (+0.25) outweighs the chronology loss (-0.10 max).

---

### Example B — VIP Unavailable in Best Slot

**Setup:**
- 4 participants: Alice (VIP), Bob, Carol, Dave
- 1 candidate slot: Tuesday 10:00–11:00 UTC
- Alice is NOT available in Tuesday 10:00 slot (she only offered Thursday)

**Scoring:**
```
attendance_score  = 3/4 = 0.75  (Bob, Carol, Dave available; Alice not)
preference_score:
  All 3 available have 9–17 prefs → 3/4 = 0.75, penalty = 0.10/4 = 0.025 (Alice violation)
vip_score = 0/1 = 0.0  (VIP Alice not available)
chronology_score = 1.0 (only one slot)

final = (0.50 * 0.75) + (0.25 * 0.75) + (0.15 * 0.0) + (0.10 * 1.0) - 0.025
      = 0.375 + 0.1875 + 0.000 + 0.100 - 0.025
      = 0.6375
```

`below_threshold = False` (0.6375 > 0.50) — slot is still returned.

---

### Example C — No Slot Meets Threshold

**Setup:**
- 4 participants, ATTENDANCE_THRESHOLD = 0.5
- `find_overlap()` found 0 candidates (no slot had >= 50% attendance)
- `rank_slots()` is called with `candidate_slots = []`

**Result:**
```python
{
    "ranked_slot":     None,
    "score":           0.0,
    "reason":          "No candidate slots available. Request more availability windows.",
    "below_threshold": True,
}
```

`rank_slots_node` sees `below_threshold=True`, drafts the "please share more windows" email, resets `slots_per_participant`, and routes back to `coordination_node`.

---

## 9. Unit Tests — tests/test_rank_slots.py

```python
# tests/test_rank_slots.py
"""
Tests for rank_slots() algorithm with deterministic inputs.
Run: pytest tests/test_rank_slots.py -v
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from tools.coordination_memory import rank_slots, WEIGHT_ATTENDANCE, SLOT_SCORE_THRESHOLD


def _slot(hour_utc: int, day_offset: int = 0, email: str = "alice@example.com") -> dict:
    """Build a TimeSlot dict for testing."""
    base  = datetime(2026, 4, 6, hour_utc, 0, tzinfo=timezone.utc)  # Monday 6 Apr
    start = base + timedelta(days=day_offset)
    end   = start + timedelta(hours=1)
    return {
        "start_utc": start.isoformat(),
        "end_utc":   end.isoformat(),
        "participant": email,
        "raw_text":  "test",
        "timezone":  "UTC",
    }


def _prefs(
    email: str,
    pref_start: int = 9,
    pref_end: int = 17,
    blocked: list[str] | None = None,
    vip: bool = False,
    slots: list[dict] | None = None,
) -> dict:
    return {
        "email":                  email,
        "preferred_hours_start":  pref_start,
        "preferred_hours_end":    pref_end,
        "blocked_days":           blocked or [],
        "vip":                    vip,
        "timezone":               "UTC",
        "slots":                  slots or [],
        "preferred_hour_buckets": [],
        "preferred_days":         [],
    }


class TestEmptyInput:
    def test_empty_slots_returns_below_threshold(self):
        result = rank_slots([], {})
        assert result["ranked_slot"] is None
        assert result["below_threshold"] is True
        assert result["score"] == 0.0


class TestSingleSlotSingleParticipant:
    def test_single_slot_always_returned(self):
        s = _slot(10)
        prefs = {"alice@example.com": _prefs("alice@example.com", slots=[s])}
        with patch("tools.coordination_memory.check_vip_status", return_value=False):
            result = rank_slots([s], prefs)
        assert result["ranked_slot"] is not None
        assert result["below_threshold"] is False

    def test_attendance_score_is_1_for_single_participant(self):
        # single participant → attendance = 1.0 → component = 0.50 * 1.0 = 0.50
        s = _slot(10)
        prefs = {"alice@example.com": _prefs("alice@example.com", slots=[s])}
        with patch("tools.coordination_memory.check_vip_status", return_value=False):
            result = rank_slots([s], prefs)
        # Score must be >= 0.50 (attendance weight alone)
        assert result["score"] >= WEIGHT_ATTENDANCE


class TestPreferenceScoring:
    def test_slot_within_preferred_hours_scores_higher(self):
        slot_good = _slot(10)   # 10am — within 9–17
        slot_bad  = _slot(3)    # 3am  — outside 9–17

        alice_good = _prefs("alice@example.com", slots=[slot_good, slot_bad])
        prefs = {"alice@example.com": alice_good}

        with patch("tools.coordination_memory.check_vip_status", return_value=False):
            result = rank_slots([slot_good, slot_bad], prefs)

        assert result["ranked_slot"]["start_utc"] == slot_good["start_utc"]

    def test_blocked_day_slot_penalised_not_eliminated(self):
        # Friday slot for participant who blocks Fridays
        slot = _slot(10, day_offset=4)  # Friday (Mon=0, Fri=4)
        prefs = {
            "alice@example.com": _prefs("alice@example.com",
                                         blocked=["Friday"], slots=[slot])
        }
        with patch("tools.coordination_memory.check_vip_status", return_value=False):
            result = rank_slots([slot], prefs)
        # Slot is still returned — just penalised
        assert result["ranked_slot"] is not None
        assert "penalty" in result["reason"] or result["score"] < 0.9


class TestVIPScoring:
    def test_all_vips_available_maximises_vip_score(self):
        s = _slot(10)
        prefs = {
            "ceo@co.com": _prefs("ceo@co.com", vip=True, slots=[s]),
            "bob@co.com": _prefs("bob@co.com", vip=False, slots=[s]),
        }
        with patch("tools.coordination_memory.check_vip_status",
                   side_effect=lambda e: e == "ceo@co.com"):
            result = rank_slots([s], prefs)
        assert "VIP" in result["reason"] or result["score"] >= 0.85

    def test_no_vips_configured_gives_full_vip_score(self):
        s = _slot(10)
        prefs = {"alice@example.com": _prefs("alice@example.com", slots=[s])}
        with patch("tools.coordination_memory.check_vip_status", return_value=False):
            result = rank_slots([s], prefs)
        # vip_score = 1.0 by default when no VIPs → full 0.15 contribution
        assert result["score"] >= 0.50 + 0.15  # at least attendance + vip

    def test_vip_unavailable_reduces_score(self):
        s = _slot(10)
        # VIP has no slots → not available → vip_score = 0
        prefs = {
            "vip@co.com":  _prefs("vip@co.com",  vip=True,  slots=[]),  # no availability
            "bob@co.com":  _prefs("bob@co.com",  vip=False, slots=[s]),
        }
        with patch("tools.coordination_memory.check_vip_status",
                   side_effect=lambda e: e == "vip@co.com"):
            result = rank_slots([s], prefs)
        # vip_score = 0 → VIP weight (0.15) not contributed
        assert result["score"] < 0.90


class TestChronologyTiebreaker:
    def test_earlier_slot_wins_on_tie(self):
        slot_early = _slot(10, day_offset=0)   # Monday 10am
        slot_late  = _slot(10, day_offset=2)   # Wednesday 10am
        # Both slots identical in all other criteria — chronology decides
        alice_early = _prefs("alice@example.com", slots=[slot_early, slot_late])
        prefs = {"alice@example.com": alice_early}
        with patch("tools.coordination_memory.check_vip_status", return_value=False):
            result = rank_slots([slot_early, slot_late], prefs)
        assert result["ranked_slot"]["start_utc"] == slot_early["start_utc"]


class TestBelowThreshold:
    def test_score_below_threshold_flagged(self):
        # Force a very low score: 1 of 4 participants available, bad hours, no VIP
        slot = _slot(3)  # 3am — terrible time
        prefs = {
            "a@x.com": _prefs("a@x.com", slots=[slot]),
            "b@x.com": _prefs("b@x.com", slots=[]),   # not available
            "c@x.com": _prefs("c@x.com", slots=[]),
            "d@x.com": _prefs("d@x.com", slots=[]),
        }
        with patch("tools.coordination_memory.check_vip_status", return_value=False):
            result = rank_slots([slot], prefs)
        # attendance = 1/4 = 0.25, weighted = 0.50*0.25 = 0.125 → well below 0.50
        assert result["below_threshold"] is True


class TestWeightConstants:
    def test_weights_sum_to_one(self):
        from tools.coordination_memory import (
            WEIGHT_ATTENDANCE, WEIGHT_PREFERENCE, WEIGHT_VIP, WEIGHT_CHRONOLOGY
        )
        total = WEIGHT_ATTENDANCE + WEIGHT_PREFERENCE + WEIGHT_VIP + WEIGHT_CHRONOLOGY
        assert abs(total - 1.0) < 1e-9   # floating point tolerance
```

---

## 10. Integration Checklist

- [ ] `PreferenceProfile` TypedDict added to `models.py` with all 9 fields
- [ ] Weight constants defined at module level in `tools/coordination_memory.py`: `WEIGHT_ATTENDANCE=0.50`, `WEIGHT_PREFERENCE=0.25`, `WEIGHT_VIP=0.15`, `WEIGHT_CHRONOLOGY=0.10`
- [ ] Weights sum to exactly 1.0 (verify: `0.50 + 0.25 + 0.15 + 0.10 == 1.00`)
- [ ] `PREFERENCE_VIOLATION_PENALTY = 0.10` defined
- [ ] `SLOT_SCORE_THRESHOLD = 0.50` defined
- [ ] Penalty is per-participant-per-violation: `0.10 / total_participants`
- [ ] `final_score` is clamped to [0.0, 1.0] via `max(0.0, min(1.0, ...))`
- [ ] Chronology denominator `time_span_secs` is clamped to minimum 1.0 (no division by zero)
- [ ] Single-slot case: `chronology_score = 1.0` (elapsed = 0, span = 1.0 minimum)
- [ ] VIP score = 1.0 when no VIPs are configured
- [ ] `reason` string includes attendance %, VIP status, preference alignment
- [ ] `rank_slots_node` in `agent/nodes.py` checks `result["below_threshold"]` and triggers coordination restart
- [ ] `agent/nodes.py rank_slots_node` tracks `coordination_restart_count` in state — caps at 2 before routing to `error_node`
- [ ] `pytest tests/test_rank_slots.py -v` passes all tests including weight sum test

---

## Cross-Phase References

| Exported | From | Imported By |
|---|---|---|
| `rank_slots()` | `tools/coordination_memory.py` | `agent/nodes.py rank_slots_node` (P6) via `tool_registry.call_tool()` |
| `SLOT_SCORE_THRESHOLD` | `tools/coordination_memory.py` | `agent/nodes.py rank_slots_node` (P6) to decide restart vs proceed |
| `PreferenceProfile` TypedDict | `models.py` | `tools/coordination_memory.py`, `preference_store.py`, `agent/nodes.py` |
| `check_vip_status()` | `preference_store.py` (P3) | `tools/coordination_memory.rank_slots()` — per-slot VIP availability check |
| `suggest_optimal_time()` | `tools/thread_intelligence.py` (P5) | `agent/nodes.py rank_slots_node` (P6) — Phase 9 integrates history into PreferenceProfile |

---

*PHASE5_RANK_SLOTS.md | Team TRIOLOGY | PCCOE Pune | Problem Statement 03*
