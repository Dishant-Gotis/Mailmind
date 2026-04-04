# PHASE11_AMBIGUITY_DETECTION.md
## Phase 11 — Ambiguity Detection Hardening (Bonus Feature)
**Covers:** `detect_ambiguity` patterns library, clarification round tracking in `AgentState`, escalation behavior, non-responsive promotion, `rank_slots()` exclusion of non-responsive participants
**Files documented:** `tools/email_coordinator.py` (ambiguity section), `models.py` (AgentState additions), `agent/nodes.py` (ambiguity/coordination), `tests/test_ambiguity_detection.py`

---

## Purpose

Emails like *"Sure, anytime works"* or *"I'm pretty free next week"* are completely non-actionable for scheduling. Phase 11 addresses this systematically. Instead of silently failing, MailMind asks the right question based on the specific vague pattern detected. If the user remains vague after two rounds, MailMind stops waiting for them — marks them as non-responsive and proceeds with the remaining participants so one ambiguous responder cannot block a group meeting indefinitely. This feature uses zero Gemini calls — it is a deterministic, regex-based pattern matcher that is fast, predictable, and testable.

---

## Dependencies

- **Phase 3:** `models.py` — `AgentState` has `ambiguity_rounds: dict` and `non_responsive: list` (verify these exist)
- **Phase 5:** `tools/email_coordinator.py` — `detect_ambiguity` tool function; the `detect_ambiguity` schema in `ALL_TOOL_SCHEMAS`
- **Phase 6:** `agent/nodes.py` — `coordination_node` calls `detect_ambiguity`; `ambiguity_node` handles escalation

---

## 1. models.py — AgentState Verification

Confirm these fields exist in `AgentState` (written in Phase 3). **Add if missing:**

```python
# models.py — AgentState TypedDict (verify from Phase 3)

class AgentState(TypedDict):
    thread_id:           str
    participants:        list[str]
    pending_responses:   list[str]
    non_responsive:      list[str]       # ← Must exist (Phase 11 writes here)
    ambiguity_rounds:    dict[str, int]  # ← Must exist: email → count of ambiguous replies
    slots_per_participant: dict[str, list[dict]]
    preferences:         dict[str, dict]
    history:             list[dict]
    intent:              str
    outbound_draft:      Optional[str]
    ranked_slot:         Optional[dict]
    rank_below_threshold: bool
    calendar_event_id:   Optional[str]
    coordination_restart_count: int
    overlap_candidates:  list[dict]
    error:               Optional[str]
    current_node:        str
```

---

## 2. Ambiguity Patterns Library — tools/email_coordinator.py

Replace the basic `detect_ambiguity` stub from Phase 5 with the full pattern library implementation.

```python
# tools/email_coordinator.py — Phase 11: Full detect_ambiguity implementation

from __future__ import annotations

import re
from logger import get_logger

logger = get_logger(__name__)


# ── Ambiguity Pattern Library ──────────────────────────────────────────────────
# Key:   regex pattern (case-insensitive, word-boundary aware)
# Value: targeted clarifying question to ask the participant
#
# Design principles:
#   - Each pattern matches a SPECIFIC vagueness type
#   - Each question requests EXACTLY what is missing
#   - Patterns are ordered from most-specific to least-specific
#   - A participant's single ambiguous email may match multiple patterns;
#     only the FIRST match is used (early return)

AMBIGUITY_PATTERNS: list[tuple[str, str]] = [
    # ── Absolute vagueness ─────────────────────────────────────────────────────
    (
        r"\banytime\b",
        "You mentioned 'anytime.' To find the best slot for everyone, could you share "
        "2-3 specific one-hour windows? For example: 'Tuesday 10am–11am IST, Wednesday 2pm–3pm IST.'"
    ),
    (
        r"\bany\s+time\b",
        "Could you provide a few specific time windows rather than 'any time'? "
        "For example: 'Monday 9am–10am, Tuesday 3pm–4pm.'"
    ),
    (
        r"\bi'?m?\s+free\s+all\s+(day|week|morning|afternoon|evening)\b",
        "Since you're free all {match}, could you specify your preferred 1-2 hour window? "
        "For example: '10am–11am' or '2pm–3pm.'"
    ),

    # ── Conditional / uncertain availability ──────────────────────────────────
    (
        r"\bshould\s+be\s+(able|free|available|ok)\b",
        "You mentioned you 'should be' available. Could you confirm your availability with "
        "specific times so I can lock in a slot for the group?"
    ),
    (
        r"\bprobably\s+(free|available|ok|fine)\b",
        "You mentioned 'probably' — could you confirm your specific available times so "
        "I can coordinate with the group? Even one concrete window helps."
    ),
    (
        r"\bmaybe\b",
        "Could you clarify? 'Maybe' makes it difficult to coordinate. Please share specific "
        "times you're definitely available."
    ),
    (
        r"\bif\s+(it\s+works|that\s+works|possible)\b",
        "Could you share 2-3 times that definitively work for you regardless of others' schedules? "
        "I'll handle the conflict resolution."
    ),

    # ── Vague relative time ───────────────────────────────────────────────────
    (
        r"\b(next\s+week|this\s+week)\b(?!.*\b(monday|tuesday|wednesday|thursday|friday|[0-9]+\s*(am|pm))\b)",
        "You mentioned next week — could you specify which days and times work for you? "
        "For example: 'Next Tuesday 10am–11am IST.'"
    ),
    (
        r"\b(tomorrow|today)\b(?!.*\b([0-9]+\s*(am|pm|:|h))\b)",
        "You mentioned tomorrow/today — great! Could you specify a time? "
        "For example: 'Tomorrow 2pm–3pm.'"
    ),
    (
        r"\b(later|sometime|soon)\b(?!\s+at\b)",
        "Could you be more specific about 'later/soon'? Please share a date and time range "
        "that works for you."
    ),

    # ── Vague time-of-day ─────────────────────────────────────────────────────
    (
        r"\b(morning)\b(?!.*[0-9])",
        "You mentioned morning — could you define your preferred morning hours? "
        "For example: '9am–10am' or '10am–11am.'"
    ),
    (
        r"\b(afternoon)\b(?!.*[0-9])",
        "You mentioned afternoon — could you specify your preferred afternoon window? "
        "For example: '2pm–3pm' or '3pm–4pm.'"
    ),
    (
        r"\b(evening)\b(?!.*[0-9])",
        "You mentioned evening — could you specify an evening slot? For example: '6pm–7pm.'"
    ),

    # ── Positive but unspecific agreement ────────────────────────────────────
    (
        r"\b(works?\s+for\s+me|that'?s?\s+(fine|ok|good|great|perfect))\b(?!.*[0-9])",
        "Glad that works for you! Could you also share 2-3 specific times you're available "
        "so I can find a slot that works for the whole group?"
    ),
    (
        r"\b(flexible|open)\b(?!.*[0-9])",
        "Since you're flexible, could you share your preferred working hours for this week? "
        "For example: 'Weekdays 9am–5pm IST.' I'll find the best overlap."
    ),

    # ── No actionable content at all ─────────────────────────────────────────
    (
        r"^\s*(ok|okay|sure|sounds\s+good|great|noted|yes|yep|yeah|👍)\s*[.!]?\s*$",
        "Thanks for confirming! To schedule the meeting, could you share your available times? "
        "For example: 'Tuesday 10am–11am IST or Wednesday 2pm–3pm IST.'"
    ),
]


def detect_ambiguity(kwargs: dict) -> dict:
    """
    Detect ambiguity in a participant's email reply.

    Scans the text for vague expressions using the AMBIGUITY_PATTERNS library.
    If a pattern matches, a targeted clarifying question is returned.
    If no pattern matches AND the text contains no parseable datetime markers,
    a generic fallback question is returned.

    Args:
        kwargs: {"text": str}  — the plain-text body of the participant's reply.

    Returns:
        dict: {
            "is_ambiguous": bool,
            "question":     str   — clarifying question (empty if not ambiguous)
        }

    Call signature (via tool_registry):
        call_tool("detect_ambiguity", {"text": email_body})

    Design:
        - Zero Gemini calls — purely deterministic regex
        - Returns on first matching pattern (most specific match wins)
        - Falls back to heuristic: no digit AND no day-of-week → ambiguous
    """
    text = kwargs.get("text", "").strip()

    if not text:
        return {
            "is_ambiguous": True,
            "question":     "Your message appears to be empty. Could you share your available times?",
        }

    text_lower = text.lower()

    # Step 1: Scan pattern library — first match wins
    for pattern, question in AMBIGUITY_PATTERNS:
        if re.search(pattern, text_lower):
            logger.info("Ambiguity detected via pattern: '%s'", pattern[:40])
            return {
                "is_ambiguous": True,
                "question":     question,
            }

    # Step 2: Heuristic fallback — if no time markers at all
    has_digit     = any(ch.isdigit() for ch in text)
    day_names     = ["monday", "tuesday", "wednesday", "thursday", "friday",
                     "saturday", "sunday", "today", "tomorrow"]
    has_day_name  = any(day in text_lower for day in day_names)
    has_time_word = any(w in text_lower for w in ["am", "pm", "noon", "midnight", "o'clock"])

    if not has_digit and not has_day_name and not has_time_word:
        logger.info("Ambiguity detected via heuristic: no time markers found.")
        return {
            "is_ambiguous": True,
            "question":     (
                "I wasn't able to extract specific times from your reply. "
                "Could you provide a concrete time window? "
                "For example: 'Tuesday 10am–11am IST.'"
            ),
        }

    return {
        "is_ambiguous": False,
        "question":     "",
    }
```

---

## 3. coordination_node — Ambiguity Integration (agent/nodes.py)

This is the exact flow sequence inside `coordination_node` for Phase 11. The node must call `detect_ambiguity` **before** `parse_availability` so we don't waste a date-parse call on a body that has no parseable times anyway.

```python
# agent/nodes.py — coordination_node (Phase 11 verified flow)

def coordination_node(state: AgentState, email_obj: dict) -> AgentState:
    thread_id = state["thread_id"]
    sender    = email_obj["sender_email"]
    sender_tz = load_preferences(sender).get("timezone", "UTC")

    try:
        # ── Step 1: Detect ambiguity FIRST ────────────────────────────────────
        amb_result = call_tool("detect_ambiguity", {"text": email_obj["body"]})

        if amb_result.get("is_ambiguous"):
            # Increment this participant's ambiguity count
            current_count = state["ambiguity_rounds"].get(sender, 0)
            state["ambiguity_rounds"][sender] = current_count + 1

            # Store the clarifying question as outbound_draft
            # ambiguity_node will check the count and decide whether to send or escalate
            state["outbound_draft"] = amb_result["question"]

            logger.info(
                "coordination_node: ambiguity detected for %s (round %d).",
                sender, current_count + 1,
                extra={"thread_id": thread_id},
            )
            return state   # Router→ ambiguity_node

        # ── Step 2: Not ambiguous → parse availability ────────────────────────
        avail_result = call_tool("parse_availability", {
            "text":      email_obj["body"],
            "sender_tz": sender_tz,
        })
        slots = avail_result.get("slots", [])

        for slot in slots:
            slot["participant"] = sender

        call_tool("track_participant_slots", {
            "thread_id": thread_id,
            "email":     sender,
            "slots":     slots,
        })

        if sender in state["pending_responses"]:
            state["pending_responses"].remove(sender)

        state["outbound_draft"] = None   # Clear any previous draft
        append_to_history(state, "user", email_obj["body"])
        append_to_history(state, "assistant", f"Parsed {len(slots)} slot(s) from {sender}.")

    except Exception as exc:
        logger.error("coordination_node error: %s", exc, extra={"thread_id": thread_id})
        state["error"] = str(exc)
        state["current_node"] = "error_node"

    return state
```

---

## 4. ambiguity_node — Escalation Logic (agent/nodes.py)

```python
# agent/nodes.py — ambiguity_node (Phase 11 verified, full implementation)

MAX_CLARIFICATION_ROUNDS = 2  # Module-level constant

def ambiguity_node(state: AgentState, email_obj: dict) -> AgentState:
    """
    Handle an ambiguous reply from a participant.

    If the participant has sent ambiguous replies FEWER than MAX_CLARIFICATION_ROUNDS times:
        → outbound_draft is already set by coordination_node; do nothing here.
          send_node will fire the clarifying question.

    If the participant has been ambiguous MAX_CLARIFICATION_ROUNDS or more times:
        → Promote them to non_responsive.
        → Remove from pending_responses (unblocks the group).
        → Clear outbound_draft (do NOT send them another message).
        → Log a warning.

    Reads:  state["ambiguity_rounds"], state["outbound_draft"]
    Writes: state["non_responsive"], state["pending_responses"], state["outbound_draft"]
    """
    thread_id = state["thread_id"]
    sender    = email_obj["sender_email"]
    rounds    = state["ambiguity_rounds"].get(sender, 0)

    if rounds >= MAX_CLARIFICATION_ROUNDS:
        # Escalation path — stop asking, mark non-responsive
        if sender not in state["non_responsive"]:
            state["non_responsive"].append(sender)
            logger.warning(
                "ambiguity_node: %s marked non-responsive after %d ambiguous rounds.",
                sender, rounds, extra={"thread_id": thread_id},
            )

        # Remove from pending so the group can proceed
        if sender in state["pending_responses"]:
            state["pending_responses"].remove(sender)

        # Do NOT send another message to this participant
        state["outbound_draft"] = None

    else:
        # Normal clarification path — outbound_draft already contains the question
        # Router will send to send_node which fires the clarifying email
        logger.info(
            "ambiguity_node: sending clarification request to %s (round %d/%d).",
            sender, rounds, MAX_CLARIFICATION_ROUNDS, extra={"thread_id": thread_id},
        )

    return state
```

---

## 5. rank_slots() — Non-Responsive Participant Exclusion

When `rank_slots_node` builds the `enriched_prefs` dict to pass into `rank_slots()`, it must exclude non-responsive participants so they do not deflate the attendance score.

```python
# agent/nodes.py — rank_slots_node (Phase 11 update)

def rank_slots_node(state: AgentState, email_obj: dict) -> AgentState:
    thread_id    = state["thread_id"]
    candidates   = state.get("overlap_candidates", [])
    non_responsive = state.get("non_responsive", [])

    # Build PreferenceProfile for RESPONSIVE participants only
    enriched_prefs = {}
    for email in state["participants"]:
        if email in non_responsive:
            continue   # ← Phase 11: exclude non-responsive from scoring entirely
        stored = load_preferences(email)
        enriched_prefs[email] = {
            **stored,
            "slots": state["slots_per_participant"].get(email, []),
        }

    # ... rest of rank_slots_node unchanged
```

**Effect on attendance_score:**
- Before Phase 11: A non-responsive participant with 0 slots drags `attendance_score` down since `total_participants` includes them.
- After Phase 11: Non-responsive participants are excluded from `total_participants` → attendance score reflects only the participants who actually provided availability.

---

## 6. All Edge Cases

| Scenario | Behaviour |
|---|---|
| Participant sends vague reply (round 1) | `ambiguity_rounds[sender] = 1`; `outbound_draft` = targeted question; sent to `send_node` |
| Participant sends vague reply again (round 2) | `ambiguity_rounds[sender] = 2`; `outbound_draft` = targeted question; sent to `send_node` |
| Participant sends vague reply again (round 3, `rounds >= MAX`) | Promoted to `non_responsive`. `outbound_draft = None`. No email sent. Group continues. |
| Participant sends clear reply after 1 vague reply | `detect_ambiguity` returns `is_ambiguous=False`. Normal parse path resumes. |
| ALL participants are non-responsive | `enriched_prefs` is empty → `rank_slots([candidates], {})` → `attendance_score=N/A` → `below_threshold=True` → `error_node` |
| Non-responsive participant is also a VIP | VIP filtered from both `non_responsive` AND `vip_participants` in `rank_slots()` (Phase 10 integration) |
| Empty email body | `detect_ambiguity({"text": ""})` returns `is_ambiguous=True` with "Your message appears to be empty..." question |
| Emoji-only reply ("👍") | Matches last pattern `^\s*(ok|...)\s*$` → `is_ambiguous=True` |

---

## 7. Unit Tests — tests/test_ambiguity_detection.py

```python
# tests/test_ambiguity_detection.py
"""
Tests for Phase 11 ambiguity detection patterns and escalation logic.
Run: pytest tests/test_ambiguity_detection.py -v
"""

from __future__ import annotations

import pytest

from tools.email_coordinator import detect_ambiguity, AMBIGUITY_PATTERNS, MAX_CLARIFICATION_ROUNDS


class TestPatternLibrary:
    """Test case 1 — Ensure pattern library covers all documented triggers."""

    def test_anytime_detected(self):
        res = detect_ambiguity({"text": "Sure, anytime next week works for me."})
        assert res["is_ambiguous"] is True
        assert "specific one-hour windows" in res["question"]

    def test_anytime_with_time_still_detected(self):
        # "anytime" overrides even if there's a vague time mention
        res = detect_ambiguity({"text": "I'm free anytime in the morning."})
        assert res["is_ambiguous"] is True

    def test_maybe_detected(self):
        res = detect_ambiguity({"text": "Maybe Friday works, not sure."})
        assert res["is_ambiguous"] is True
        assert "definitely" in res["question"]

    def test_flexible_detected(self):
        res = detect_ambiguity({"text": "I'm pretty flexible this week."})
        assert res["is_ambiguous"] is True
        assert "working hours" in res["question"]

    def test_works_for_me_without_time_detected(self):
        res = detect_ambiguity({"text": "Works for me!"})
        assert res["is_ambiguous"] is True

    def test_next_week_without_specific_day_detected(self):
        res = detect_ambiguity({"text": "Next week should be fine."})
        assert res["is_ambiguous"] is True

    def test_tomorrow_without_time_detected(self):
        res = detect_ambiguity({"text": "I can do tomorrow."})
        assert res["is_ambiguous"] is True

    def test_morning_without_hour_detected(self):
        res = detect_ambiguity({"text": "Morning works best for me."})
        assert res["is_ambiguous"] is True
        assert "morning hours" in res["question"]

    def test_emoji_only_reply_detected(self):
        res = detect_ambiguity({"text": "👍"})
        assert res["is_ambiguous"] is True

    def test_ok_only_reply_detected(self):
        res = detect_ambiguity({"text": "ok"})
        assert res["is_ambiguous"] is True

    def test_empty_body_detected(self):
        res = detect_ambiguity({"text": ""})
        assert res["is_ambiguous"] is True
        assert "empty" in res["question"]


class TestClearReplies:
    """Test case 2 — Clear, parseable replies must NOT be flagged as ambiguous."""

    def test_specific_time_not_ambiguous(self):
        res = detect_ambiguity({"text": "I'm available Tuesday 10am–11am IST."})
        assert res["is_ambiguous"] is False
        assert res["question"] == ""

    def test_numeric_time_not_ambiguous(self):
        res = detect_ambiguity({"text": "How about 14:00 UTC on Monday?"})
        assert res["is_ambiguous"] is False

    def test_next_week_with_specific_day_not_ambiguous(self):
        res = detect_ambiguity({"text": "Next Tuesday at 10am works."})
        assert res["is_ambiguous"] is False

    def test_works_for_me_with_time_not_ambiguous(self):
        res = detect_ambiguity({"text": "Works for me — 3pm on Thursday."})
        assert res["is_ambiguous"] is False

    def test_morning_with_hour_not_ambiguous(self):
        res = detect_ambiguity({"text": "Morning, around 9am, works for me."})
        # "morning" pattern should NOT match because text contains digits
        assert res["is_ambiguous"] is False


class TestHeuristicFallback:
    """Test case 3 — Heuristic fallback for replies with no time markers."""

    def test_no_time_markers_detected(self):
        res = detect_ambiguity({"text": "Sounds good to me, let's do it."})
        assert res["is_ambiguous"] is True
        assert "concrete time window" in res["question"]

    def test_reply_with_name_only_detected(self):
        res = detect_ambiguity({"text": "This is Alice. I agree to the meeting."})
        assert res["is_ambiguous"] is True


class TestAmbiguityNodeEscalation:
    """Test case 4 — ambiguity_node escalation logic."""

    def _make_state(self, rounds: int, sender: str) -> dict:
        return {
            "thread_id":          "t001",
            "ambiguity_rounds":   {sender: rounds},
            "non_responsive":     [],
            "pending_responses":  [sender, "bob@example.com"],
            "outbound_draft":     "Please clarify your availability.",
        }

    def _make_email(self, sender: str) -> dict:
        return {"sender_email": sender}

    def test_below_max_rounds_keeps_draft(self):
        from agent.nodes import ambiguity_node
        state  = self._make_state(1, "alice@example.com")
        result = ambiguity_node(state, self._make_email("alice@example.com"))
        # Draft preserved — will be sent
        assert result["outbound_draft"] is not None
        assert "alice@example.com" not in result["non_responsive"]

    def test_at_max_rounds_promotes_to_non_responsive(self):
        from agent.nodes import ambiguity_node
        state  = self._make_state(2, "alice@example.com")
        result = ambiguity_node(state, self._make_email("alice@example.com"))
        # Escalated
        assert "alice@example.com" in result["non_responsive"]
        assert "alice@example.com" not in result["pending_responses"]
        assert result["outbound_draft"] is None

    def test_other_participants_unaffected(self):
        from agent.nodes import ambiguity_node
        state  = self._make_state(2, "alice@example.com")
        result = ambiguity_node(state, self._make_email("alice@example.com"))
        # Bob is unaffected
        assert "bob@example.com" in result["pending_responses"]

    def test_escalation_idempotent(self):
        """Second call with same participant who is already non-responsive."""
        from agent.nodes import ambiguity_node
        state = self._make_state(3, "alice@example.com")
        state["non_responsive"] = ["alice@example.com"]  # already there
        result = ambiguity_node(state, self._make_email("alice@example.com"))
        # Should not duplicate
        assert result["non_responsive"].count("alice@example.com") == 1


class TestNonResponsiveExclusion:
    """Test case 5 — Non-responsive participants excluded from rank_slots scoring."""

    def test_non_responsive_excluded_from_enriched_prefs(self):
        """Simulate rank_slots_node building enriched_prefs."""
        from unittest.mock import patch, MagicMock
        from datetime import datetime, timezone

        slot = {
            "start_utc": datetime(2026, 4, 7, 9, 0, tzinfo=timezone.utc).isoformat(),
            "end_utc":   datetime(2026, 4, 7, 10, 0, tzinfo=timezone.utc).isoformat(),
            "participant": "test", "raw_text": "", "timezone": "UTC",
        }
        state = {
            "thread_id":          "t001",
            "participants":       ["alice@example.com", "bob@example.com"],
            "non_responsive":     ["alice@example.com"],   # Alice is non-responsive
            "slots_per_participant": {"bob@example.com": [slot]},
            "overlap_candidates": [slot],
            "preferences":        {},
            "ranked_slot":        None,
            "rank_below_threshold": True,
            "coordination_restart_count": 0,
            "outbound_draft":     None,
            "pending_responses":  [],
        }

        with patch("agent.nodes.load_preferences", return_value={
            "email": "bob@example.com", "preferred_hours_start": 9, "preferred_hours_end": 17,
            "blocked_days": [], "vip": False, "timezone": "UTC",
            "slots": [slot], "preferred_hour_buckets": [], "preferred_days": [],
        }), patch("agent.nodes.call_tool") as mock_call:
            mock_call.return_value = {
                "ranked_slot": slot, "score": 0.85, "reason": "test", "below_threshold": False
            }
            from agent.nodes import rank_slots_node
            email_obj = {"sender_email": "bob@example.com"}
            result = rank_slots_node(state, email_obj)

            # call_tool was called with only BOB's preferences (Alice excluded)
            call_args = mock_call.call_args_list[-1]
            passed_prefs = call_args[0][1]["preferences"]
            assert "alice@example.com" not in passed_prefs
            assert "bob@example.com" in passed_prefs


class TestMaxClarificationRoundsConstant:
    def test_max_rounds_is_two(self):
        from agent.nodes import MAX_CLARIFICATION_ROUNDS
        assert MAX_CLARIFICATION_ROUNDS == 2

    def test_pattern_count_is_adequate(self):
        # The library must have at least 15 patterns
        assert len(AMBIGUITY_PATTERNS) >= 15
```

---

## 8. Integration Checklist

- [ ] `AgentState` in `models.py` has `ambiguity_rounds: dict[str, int]` and `non_responsive: list[str]`
- [ ] `AMBIGUITY_PATTERNS` list has at minimum 15 entries covering all documented pattern types
- [ ] Each pattern uses `re.search()` against lowercased text — NOT `re.match()` (match only checks start of string)
- [ ] Empty body returns `is_ambiguous=True` with empty-message question
- [ ] Clear replies with digit + day name return `is_ambiguous=False`
- [ ] `coordination_node` calls `detect_ambiguity` BEFORE `parse_availability`
- [ ] `coordination_node` increments `ambiguity_rounds[sender]` when ambiguity detected
- [ ] `ambiguity_node` checks `rounds >= MAX_CLARIFICATION_ROUNDS` (not `>`)
- [ ] `ambiguity_node` does NOT DUPLICATE entries in `non_responsive` list (idempotent)
- [ ] `ambiguity_node` does NOT send any email when escalating (clears `outbound_draft = None`)
- [ ] `rank_slots_node` excludes non-responsive participants from `enriched_prefs` dict
- [ ] `MAX_CLARIFICATION_ROUNDS = 2` defined at module level in `agent/nodes.py`
- [ ] `pytest tests/test_ambiguity_detection.py -v` passes all 5 test classes

---

## Cross-Phase References

| Exported | From | Imported By |
|---|---|---|
| `detect_ambiguity()` | `tools/email_coordinator.py` | `agent/nodes.py coordination_node` (P6) via `call_tool("detect_ambiguity", ...)` |
| `AMBIGUITY_PATTERNS` | `tools/email_coordinator.py` | `tests/test_ambiguity_detection.py` (pattern count check) |
| `MAX_CLARIFICATION_ROUNDS` | `agent/nodes.py` | `agent/nodes.py ambiguity_node`; `tests/test_ambiguity_detection.py` |
| `non_responsive: list[str]` | `AgentState` (models.py P3) | `agent/nodes.py ambiguity_node`, `rank_slots_node`; `tools/coordination_memory.rank_slots()` (P5) |
| `ambiguity_rounds: dict` | `AgentState` (models.py P3) | `agent/nodes.py coordination_node`, `ambiguity_node` |

---

*PHASE11_AMBIGUITY_DETECTION.md | Team TRIOLOGY | PCCOE Pune | Problem Statement 03*
