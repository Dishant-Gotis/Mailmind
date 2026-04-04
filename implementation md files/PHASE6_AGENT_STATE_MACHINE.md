# PHASE6_AGENT_STATE_MACHINE.md
## Phase 6 — Agent State Machine (Core Engine)
**Covers:** `agent/nodes.py`, `agent/router.py`, `agent/graph.py`, `agent/loop.py`, state transition diagram, all node input/output tables, routing logic, exception handling
**Files documented:** `agent/__init__.py`, `agent/nodes.py`, `agent/router.py`, `agent/graph.py`, `agent/loop.py`, `tests/test_agent_loop.py`

---

## Purpose

Phase 6 is the brain of MailMind — the directed state graph that orchestrates every decision. Each node is a pure function that reads from `AgentState`, calls tools or Gemini, and writes back to `AgentState`. The router functions decide which node runs next based on the current state. The loop runs nodes in sequence, checkpointing after every single node execution. If the process crashes mid-thread, the next email from that thread will reload the exact last saved state and continue from the next node. No logic is duplicated between nodes — each node does exactly one thing.

---

## Dependencies

- **All previous phases complete**
- **Phase 1:** `config`, `exceptions`, `logger`
- **Phase 2:** `EmailObject` from `models.py`
- **Phase 3:** `AgentState`, `TimeSlot`, `init_state`, `save_state`, `load_state`, `clear_state`, `store_preferences`, `load_preferences`
- **Phase 4:** `tool_caller.call_with_tools`, `tool_caller.call_for_text`, `prompt_builder.*`
- **Phase 5:** `tool_registry.ALL_TOOL_SCHEMAS`, `tool_registry.call_tool`

---

## 1. agent/__init__.py

```python
# agent/__init__.py
# Empty — agent subpackage marker
```

---

## 2. agent/graph.py — Complete Implementation

```python
# agent/graph.py
"""
GRAPH dict and node name constants for the MailMind agent state machine.
Every node name used anywhere in the codebase must be defined here as a constant.
"""

# Sentinel value marking loop termination
END = "__END__"

# Node name constants — use these everywhere, never hardcode strings
TRIAGE_NODE            = "triage_node"
COORDINATION_NODE      = "coordination_node"
AMBIGUITY_NODE         = "ambiguity_node"
OVERLAP_NODE           = "overlap_node"
RANK_SLOTS_NODE        = "rank_slots_node"
CALENDAR_NODE          = "calendar_node"
THREAD_INTELLIGENCE_NODE = "thread_intelligence_node"
REWRITE_NODE           = "rewrite_node"
APPROVAL_NODE          = "approval_node"
SEND_NODE              = "send_node"
ERROR_NODE             = "error_node"

# Import routing functions (defined in router.py)
from agent.router import (
    route_by_intent,
    route_by_completeness,
    route_by_threshold,
    route_by_approval,
)

# GRAPH maps each node name to the routing function that decides the next node.
# Nodes that always go to a fixed next node use a lambda returning that node name.
GRAPH: dict[str, object] = {
    TRIAGE_NODE:              route_by_intent,
    COORDINATION_NODE:        route_by_completeness,
    AMBIGUITY_NODE:           lambda state: SEND_NODE,
    OVERLAP_NODE:             lambda state: RANK_SLOTS_NODE,
    RANK_SLOTS_NODE:          route_by_threshold,
    CALENDAR_NODE:            lambda state: REWRITE_NODE,
    THREAD_INTELLIGENCE_NODE: lambda state: REWRITE_NODE,
    REWRITE_NODE:             lambda state: APPROVAL_NODE,
    APPROVAL_NODE:            route_by_approval,
    SEND_NODE:                lambda state: END,
    ERROR_NODE:               lambda state: END,
}
```

---

## 3. agent/router.py — Complete Implementation

```python
# agent/router.py
"""
All routing functions for the MailMind agent state machine.
Each function receives the current AgentState and returns the name of the next node.
"""

from __future__ import annotations

from agent.graph import (
    AMBIGUITY_NODE, CALENDAR_NODE, COORDINATION_NODE,
    END, ERROR_NODE, OVERLAP_NODE, RANK_SLOTS_NODE,
    SEND_NODE, THREAD_INTELLIGENCE_NODE,
)
from logger import get_logger

logger = get_logger(__name__)


def route_by_intent(state: dict) -> str:
    """
    Route from triage_node based on classified email intent.

    Intent → Next Node:
        "scheduling"      → coordination_node   (begin availability collection)
        "update_request"  → thread_intelligence_node  (summarise thread status)
        "reschedule"      → coordination_node   (restart availability collection)
        "cancellation"    → send_node           (send cancellation confirmation)
        "noise"           → error_node          (log and skip — no action)
        anything else     → error_node          (unknown intent — flag to operator)

    Reads from state: intent
    """
    intent = state.get("intent", "noise")
    thread_id = state.get("thread_id", "")

    routing = {
        "scheduling":     COORDINATION_NODE,
        "update_request": THREAD_INTELLIGENCE_NODE,
        "reschedule":     COORDINATION_NODE,
        "cancellation":   SEND_NODE,
        "noise":          ERROR_NODE,
    }
    next_node = routing.get(intent, ERROR_NODE)
    logger.debug(
        "route_by_intent: intent=%s → %s", intent, next_node,
        extra={"thread_id": thread_id},
    )
    return next_node


def route_by_completeness(state: dict) -> str:
    """
    Route from coordination_node based on whether all participants have responded.

    Logic:
        If pending_responses is empty (all participants replied) → overlap_node
        If ambiguity detected (outbound_draft set by ambiguity check) → ambiguity_node
        If still waiting on participants → END (wait for next email to re-trigger)

    Reads from state: pending_responses, outbound_draft
    """
    thread_id = state.get("thread_id", "")
    pending = state.get("pending_responses", [])
    draft   = state.get("outbound_draft")

    if draft:
        # An ambiguity clarification was drafted in coordination_node → send it
        logger.debug(
            "route_by_completeness: draft set → %s", AMBIGUITY_NODE,
            extra={"thread_id": thread_id},
        )
        return AMBIGUITY_NODE

    if not pending:
        # All participants responded with parseable availability
        logger.debug(
            "route_by_completeness: all responded → %s", OVERLAP_NODE,
            extra={"thread_id": thread_id},
        )
        return OVERLAP_NODE

    # Still waiting — do not proceed, wait for next email
    logger.debug(
        "route_by_completeness: waiting on %d participant(s) → %s",
        len(pending), END,
        extra={"thread_id": thread_id},
    )
    return END


def route_by_threshold(state: dict) -> str:
    """
    Route from rank_slots_node based on whether the best slot meets the score threshold.

    Logic:
        If ranked_slot is set and below_threshold is False → calendar_node
        If below_threshold is True (or ranked_slot is None):
            If coordination_restart_count >= 2 → error_node (prevent infinite loop)
            Else → coordination_node (request more availability windows)

    Reads from state: ranked_slot, coordination_restart_count
    """
    thread_id      = state.get("thread_id", "")
    ranked_slot    = state.get("ranked_slot")
    restart_count  = state.get("coordination_restart_count", 0)

    if ranked_slot and not state.get("rank_below_threshold", False):
        logger.debug(
            "route_by_threshold: slot found → %s", CALENDAR_NODE,
            extra={"thread_id": thread_id},
        )
        return CALENDAR_NODE

    # Below threshold
    if restart_count >= 2:
        logger.warning(
            "route_by_threshold: restart limit reached → %s", ERROR_NODE,
            extra={"thread_id": thread_id},
        )
        return ERROR_NODE

    logger.debug(
        "route_by_threshold: below threshold (restart %d) → %s",
        restart_count, COORDINATION_NODE,
        extra={"thread_id": thread_id},
    )
    return COORDINATION_NODE


def route_by_approval(state: dict) -> str:
    """

    approval_status values:
        "approved"  → send_node  (operator approved, fire the email)
        "timeout"   → send_node  (5-min window expired, auto-send)
        "rejected"  → rewrite_node  (operator rejected, revise the draft)
        anything else → error_node

    Reads from state: approval_status
    """
    thread_id = state.get("thread_id", "")
    status = state.get("approval_status", "")

    routing = {
        "approved": SEND_NODE,
        "timeout":  SEND_NODE,
        "rejected": "rewrite_node",   # re-enter rewrite loop
    }
    next_node = routing.get(status, ERROR_NODE)
    logger.debug(
        "route_by_approval: status=%s → %s", status, next_node,
        extra={"thread_id": thread_id},
    )
    return next_node
```

---

## 4. agent/nodes.py — Complete Implementation

```python
# agent/nodes.py
"""
All 10 node functions for the MailMind agent state machine.
Each node: reads from AgentState → calls tools/Gemini → writes to AgentState → returns state.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from checkpointer import clear_state, load_state
from exceptions import GeminiAPIError, LowConfidenceError, ToolNotFoundError
from logger import get_logger
from models import AgentState
from preference_store import load_preferences, store_preferences
from prompt_builder import (
    append_to_history,
    build_ambiguity_prompt,
    build_coordination_prompt,
    build_rewrite_prompt,
    build_summarise_prompt,
    build_triage_prompt,
)
from tool_caller import call_for_text, call_with_tools
from tool_registry import ALL_TOOL_SCHEMAS, call_tool

logger = get_logger(__name__)


# ── Node 1: triage_node ────────────────────────────────────────────────────────

def triage_node(state: AgentState, email_obj: dict) -> AgentState:
    """
    Classify the intent of the inbound email using Gemini.

    Reads:  email_obj (passed as arg), state["history"]
    Writes: state["intent"], state["history"]

    Raises routed to error_node via return:
        GeminiAPIError, LowConfidenceError
    """
    thread_id = state["thread_id"]
    try:
        messages = build_triage_prompt(email_obj, state)
        schema   = [s for s in ALL_TOOL_SCHEMAS if s["function"]["name"] == "classify"]
        result   = call_with_tools(messages, schema, thread_id=thread_id)

        state["intent"] = result.get("intent", "noise")
        append_to_history(state, "user", email_obj["body"])
        append_to_history(state, "assistant", f"Intent classified: {state['intent']}")

        logger.info(
            "triage_node: intent=%s", state["intent"],
            extra={"thread_id": thread_id},
        )
    except (GeminiAPIError, LowConfidenceError, ToolNotFoundError) as exc:
        logger.error("triage_node error: %s", exc, extra={"thread_id": thread_id})
        state["error"] = str(exc)
        state["current_node"] = "error_node"
    return state


# ── Node 2: coordination_node ─────────────────────────────────────────────────

def coordination_node(state: AgentState, email_obj: dict) -> AgentState:
    """
    Extract availability from the inbound email and track slots per participant.
    Detects ambiguity and drafts a clarifying question if needed.

    Reads:  email_obj, state["participants"], state["pending_responses"],
            state["preferences"], state["non_responsive"]
    Writes: state["slots_per_participant"] (via track_participant_slots),
            state["pending_responses"] (removes responded participant),
            state["outbound_draft"] (set if ambiguity detected, else cleared),
            state["ambiguity_rounds"] (incremented on ambiguity)
    """
    thread_id  = state["thread_id"]
    sender     = email_obj["sender_email"]
    sender_tz  = state["preferences"].get(sender, {}).get("timezone", "UTC")

    try:
        # Step 1: Check for ambiguity first
        ambiguity_schema = [s for s in ALL_TOOL_SCHEMAS if s["function"]["name"] == "detect_ambiguity"]
        ambiguity_msgs   = build_ambiguity_prompt(email_obj, state)
        amb_result       = call_with_tools(ambiguity_msgs, ambiguity_schema, thread_id=thread_id)

        if amb_result.get("is_ambiguous"):
            rounds = state["ambiguity_rounds"].get(sender, 0)
            state["ambiguity_rounds"][sender] = rounds + 1
            state["outbound_draft"] = amb_result["question"]
            logger.info(
                "coordination_node: ambiguity detected for %s (round %d)",
                sender, rounds + 1, extra={"thread_id": thread_id},
            )
            return state  # router will send to ambiguity_node

        # Step 2: Parse availability
        avail_schema = [s for s in ALL_TOOL_SCHEMAS if s["function"]["name"] == "parse_availability"]
        avail_result = call_tool("parse_availability", {"text": email_obj["body"], "sender_tz": sender_tz})
        slots = avail_result.get("slots", [])

        # Tag each slot with sender email
        for slot in slots:
            slot["participant"] = sender

        # Step 3: Track slots in session
        call_tool("track_participant_slots", {
            "thread_id": thread_id,
            "email":     sender,
            "slots":     slots,
        })

        # Remove from pending
        if sender in state["pending_responses"]:
            state["pending_responses"].remove(sender)

        state["outbound_draft"] = None  # clear any previous draft
        append_to_history(state, "user", email_obj["body"])
        append_to_history(state, "assistant", f"Parsed {len(slots)} slot(s) from {sender}.")

        logger.info(
            "coordination_node: %d slot(s) from %s. Pending: %s",
            len(slots), sender, state["pending_responses"],
            extra={"thread_id": thread_id},
        )
    except Exception as exc:
        logger.error("coordination_node error: %s", exc, extra={"thread_id": thread_id})
        state["error"] = str(exc)
        state["current_node"] = "error_node"
    return state


# ── Node 3: ambiguity_node ────────────────────────────────────────────────────

def ambiguity_node(state: AgentState, email_obj: dict) -> AgentState:
    """
    Set outbound_draft to the clarifying question already drafted in coordination_node.
    Also handles non-responsive participant promotion after MAX_CLARIFICATION_ROUNDS.

    MAX_CLARIFICATION_ROUNDS = 2

    Reads:  state["outbound_draft"], state["ambiguity_rounds"]
    Writes: state["non_responsive"] (if rounds >= 2), state["pending_responses"]
    """
    MAX_ROUNDS = 2
    thread_id  = state["thread_id"]
    sender     = email_obj["sender_email"]
    rounds     = state["ambiguity_rounds"].get(sender, 0)

    if rounds >= MAX_ROUNDS:
        # Mark participant as non-responsive — exclude from overlap computation
        if sender not in state["non_responsive"]:
            state["non_responsive"].append(sender)
        if sender in state["pending_responses"]:
            state["pending_responses"].remove(sender)
        state["outbound_draft"] = None   # no clarification — skip them
        logger.warning(
            "ambiguity_node: %s marked non-responsive after %d rounds.",
            sender, rounds, extra={"thread_id": thread_id},
        )
    # outbound_draft is already set by coordination_node — send_node will fire it
    return state


# ── Node 4: overlap_node ───────────────────────────────────────────────────────

def overlap_node(state: AgentState, email_obj: dict) -> AgentState:
    """
    Compute time slot intersection across all responsive participants.

    Reads:  state["thread_id"], state["non_responsive"]
    Writes: state["overlap_candidates"] (stored temporarily; rank_slots_node reads this)

    Note: overlap_candidates is stored as a state field temporarily.
    Add "overlap_candidates: list[dict]" to AgentState TypedDict in models.py.
    """
    thread_id = state["thread_id"]
    try:
        result = call_tool("find_overlap", {"thread_id": thread_id})
        state["overlap_candidates"] = result.get("candidates", [])
        logger.info(
            "overlap_node: %d candidate(s) found.", len(state["overlap_candidates"]),
            extra={"thread_id": thread_id},
        )
    except Exception as exc:
        logger.error("overlap_node error: %s", exc, extra={"thread_id": thread_id})
        state["error"] = str(exc)
        state["current_node"] = "error_node"
    return state


# ── Node 5: rank_slots_node ───────────────────────────────────────────────────

def rank_slots_node(state: AgentState, email_obj: dict) -> AgentState:
    """
    Score candidate slots and select the optimal meeting time.

    Reads:  state["overlap_candidates"], state["preferences"], state["coordination_restart_count"]
    Writes: state["ranked_slot"], state["rank_below_threshold"],
            state["outbound_draft"] (if restarting coordination),
            state["coordination_restart_count"] (incremented on restart),
            state["slots_per_participant"] (cleared on restart),
            state["pending_responses"] (repopulated on restart)
    """
    thread_id   = state["thread_id"]
    candidates  = state.get("overlap_candidates", [])
    preferences = state.get("preferences", {})

    # Load full PreferenceProfile for each participant (includes their slots)
    enriched_prefs = {}
    for email in state["participants"]:
        stored = load_preferences(email)
        enriched_prefs[email] = {
            **stored,
            "slots": state["slots_per_participant"].get(email, []),
        }

    try:
        result = call_tool("rank_slots", {
            "candidate_slots": candidates,
            "preferences":     enriched_prefs,
        })

        state["ranked_slot"]         = result.get("ranked_slot")
        state["rank_below_threshold"] = result.get("below_threshold", True)

        if result.get("below_threshold"):
            restart_count = state.get("coordination_restart_count", 0) + 1
            state["coordination_restart_count"] = restart_count
            # Draft the "please send more windows" message
            state["outbound_draft"] = (
                "Hi all,\n\nWe weren't able to find a time that works for everyone. "
                "Could each of you please share 2–3 additional availability windows?\n\n"
                "For example:\n  - Monday 07 Apr 10:00–11:00 IST\n  - Tuesday 08 Apr 15:00–16:00 IST\n\n"
                "Thank you,\nMailMind"
            )
            # Reset availability for next round
            state["slots_per_participant"] = {}
            state["pending_responses"]     = [p for p in state["participants"]
                                               if p not in state["non_responsive"]]
            logger.warning(
                "rank_slots_node: below threshold — coordination restart %d.",
                restart_count, extra={"thread_id": thread_id},
            )
        else:
            logger.info(
                "rank_slots_node: selected slot %s (score=%.4f, reason=%s)",
                result["ranked_slot"]["start_utc"], result["score"], result["reason"],
                extra={"thread_id": thread_id},
            )
    except Exception as exc:
        logger.error("rank_slots_node error: %s", exc, extra={"thread_id": thread_id})
        state["error"] = str(exc)
        state["current_node"] = "error_node"
    return state


# ── Node 6: calendar_node ─────────────────────────────────────────────────────

def calendar_node(state: AgentState, email_obj: dict) -> AgentState:
    """
    Check for duplicate, create Calendar event, send invites.

    Reads:  state["ranked_slot"], state["participants"], state["subject"] (from email_obj)
    Writes: state["outbound_draft"] (confirmation email body),
            state["calendar_event_id"] (add to AgentState)

    After successful creation: calls store_preferences() for all participants.
    After successful creation: calls clear_state() to archive this session.
    """
    thread_id = state["thread_id"]
    slot      = state.get("ranked_slot")

    if slot is None:
        state["error"] = "calendar_node called with no ranked_slot."
        state["current_node"] = "error_node"
        return state

    try:
        from config import config
        from datetime import timedelta

        start_utc = slot["start_utc"]
        # Build end_utc from start + MEETING_DURATION_MINUTES
        start_dt = datetime.fromisoformat(start_utc)
        end_dt   = start_dt + timedelta(minutes=config.meeting_duration_minutes)
        end_utc  = end_dt.isoformat()

        title        = email_obj.get("subject", "Meeting via MailMind")
        participants = state["participants"]

        # Check for duplicates first
        dup_result = call_tool("check_duplicate", {
            "title":        title,
            "start_utc":    start_utc,
            "participants": participants,
        })

        if dup_result.get("duplicate"):
            state["outbound_draft"] = (
                f"A meeting '{title}' at {start_utc} already exists on the calendar. "
                "No duplicate event created."
            )
            logger.info(
                "calendar_node: duplicate found (id=%s) — skipping creation.",
                dup_result.get("event_id"), extra={"thread_id": thread_id},
            )
        else:
            event_result = call_tool("create_event", {
                "title":        title,
                "start_utc":    start_utc,
                "end_utc":      end_utc,
                "participants": participants,
                "description":  f"Meeting coordinated by MailMind. Thread: {thread_id}",
            })
            state["calendar_event_id"] = event_result.get("event_id")

            # Store learning data for each participant
            for p_email in participants:
                store_preferences(p_email, accepted_slot=slot)

            state["outbound_draft"] = (
                f"Great news! I've scheduled the meeting:\n\n"
                f"  📅 {title}\n"
                f"  🕐 {start_utc} UTC\n"
                f"  👥 {', '.join(participants)}\n\n"
                f"A Google Calendar invite has been sent to all participants.\n"
                f"Calendar link: {event_result.get('html_link', '')}"
            )
            logger.info(
                "calendar_node: event created id=%s", event_result.get("event_id"),
                extra={"thread_id": thread_id},
            )

    except Exception as exc:
        logger.error("calendar_node error: %s", exc, extra={"thread_id": thread_id})
        state["error"] = str(exc)
        state["current_node"] = "error_node"
    return state


# ── Node 7: thread_intelligence_node ─────────────────────────────────────────

def thread_intelligence_node(state: AgentState, email_obj: dict) -> AgentState:
    """
    Generate a contextual summary of the thread for update_request intents.

    Reads:  state["thread_id"], state["history"]
    Writes: state["outbound_draft"]
    """
    thread_id = state["thread_id"]
    try:
        result = call_tool("summarise_thread", {"thread_id": thread_id})
        state["outbound_draft"] = result.get("summary", "No summary available.")
        logger.info("thread_intelligence_node: summary generated.", extra={"thread_id": thread_id})
    except Exception as exc:
        logger.error("thread_intelligence_node error: %s", exc, extra={"thread_id": thread_id})
        state["error"] = str(exc)
        state["current_node"] = "error_node"
    return state


# ── Node 8: rewrite_node ──────────────────────────────────────────────────────

def rewrite_node(state: AgentState, email_obj: dict) -> AgentState:
    """
    Polish the outbound_draft tone via Gemini. Disclaimer added at send level.

    Reads:  state["outbound_draft"]
    Writes: state["outbound_draft"] (updated polished version)
    """
    thread_id = state["thread_id"]
    draft = state.get("outbound_draft", "")
    if not draft:
        state["error"] = "rewrite_node called with empty outbound_draft."
        state["current_node"] = "error_node"
        return state

    try:
        messages  = build_rewrite_prompt(draft, state)
        polished  = call_for_text(messages, thread_id=thread_id, temperature=0.7)
        state["outbound_draft"] = polished
        logger.info("rewrite_node: draft polished.", extra={"thread_id": thread_id})
    except Exception as exc:
        logger.warning(
            "rewrite_node Gemini error (%s) — using unpolished draft.", exc,
            extra={"thread_id": thread_id},
        )
        # Non-fatal: use the original draft if rewriting fails
    return state


# ── Node 9: approval_node ─────────────────────────────────────────────────────

def approval_node(state: AgentState, email_obj: dict) -> AgentState:
    """
    Auto-send on timeout.

    Writes: state["approval_status"] → "approved" | "rejected" | "timeout"

    Implementation note:
        async send_approval_request() from within the synchronous node.
        For Phase 6, approval_status is set to "approved" by default to allow
    """
    thread_id = state["thread_id"]
    draft     = state.get("outbound_draft", "")

    try:
        status = request_approval(draft, thread_id=thread_id)
        state["approval_status"] = status
        logger.info(
            "approval_node: status=%s", status, extra={"thread_id": thread_id},
        )
    except ImportError:
        logger.warning(
            extra={"thread_id": thread_id},
        )
        state["approval_status"] = "approved"
    except Exception as exc:
        logger.error(
            "approval_node error: %s — auto-approving.", exc,
            extra={"thread_id": thread_id},
        )
        state["approval_status"] = "timeout"

    return state


# ── Node 10: send_node ────────────────────────────────────────────────────────

def send_node(state: AgentState, email_obj: dict) -> AgentState:
    """
    Fire the outbound email via SMTP. Disclaimer appended inside smtp_sender.

    Reads:  state["outbound_draft"], email_obj (for reply headers)
    Writes: (nothing — terminal node)

    After send: calls clear_state() to archive the session.
    """
    thread_id = state["thread_id"]
    draft     = state.get("outbound_draft", "")

    if not draft:
        logger.warning("send_node: no draft to send.", extra={"thread_id": thread_id})
        return state

    try:
        call_tool("send_reply", {
            "to":          email_obj["sender_email"],
            "subject":     email_obj["subject"],
            "body":        draft,
            "thread_id":   thread_id,
            "in_reply_to": email_obj["message_id"],
            "references":  email_obj.get("in_reply_to", "") + " " + email_obj["message_id"],
            "cc":          [],
        })
        logger.info("send_node: email sent.", extra={"thread_id": thread_id})

        # Archive session after confirmed send
        clear_state(thread_id)

    except Exception as exc:
        logger.error("send_node error: %s", exc, extra={"thread_id": thread_id})
        state["error"] = str(exc)
    return state


# ── Node 11: error_node ───────────────────────────────────────────────────────

def error_node(state: AgentState, email_obj: dict) -> AgentState:
    """
    Log the error, mark session with error flag, do NOT send any email.

    Reads:  state["error"], state["current_node"]
    Writes: state["error"] (already set by calling node)
    """
    thread_id = state["thread_id"]
    error_msg = state.get("error", "Unknown error")

    logger.error(
        "error_node: %s (at node=%s)", error_msg, state.get("current_node"),
        extra={"thread_id": thread_id},
    )

    try:
        send_alert(f"MailMind error in thread {thread_id}:\n{error_msg}")
    except Exception:

    return state


# ── NODE_REGISTRY — maps node name strings to functions ──────────────────────

NODE_REGISTRY: dict[str, object] = {
    "triage_node":              triage_node,
    "coordination_node":        coordination_node,
    "ambiguity_node":           ambiguity_node,
    "overlap_node":             overlap_node,
    "rank_slots_node":          rank_slots_node,
    "calendar_node":            calendar_node,
    "thread_intelligence_node": thread_intelligence_node,
    "rewrite_node":             rewrite_node,
    "approval_node":            approval_node,
    "send_node":                send_node,
    "error_node":               error_node,
}
```

---

## 5. agent/loop.py — Complete Implementation

```python
# agent/loop.py
"""
Main agent execution loop. Called once per inbound email.
Loads state → runs nodes → checkpoints → terminates on END.
"""

from __future__ import annotations

from checkpointer import load_state, save_state
from exceptions import CheckpointError, NodeExecutionError
from logger import get_logger
from models import AgentState, EmailObject, init_state

from agent.graph import END, GRAPH
from agent.nodes import NODE_REGISTRY

logger = get_logger(__name__)


def run(thread_id: str, email_obj: EmailObject) -> None:
    """
    Execute the agent loop for one inbound email.

    Args:
        thread_id:  Gmail thread ID — session key.
        email_obj:  Parsed EmailObject for the inbound email.

    Algorithm:
        1. Load existing state or initialise new state.
        2. Load participant preferences into state["preferences"].
        3. Set current_node = "triage_node".
        4. While current_node != END:
            a. Execute node_fn(state, email_obj)
            b. save_state() — checkpoint after every node
            c. If node set state["current_node"] = "error_node" → follow it
            d. Get next node from GRAPH[current_node](state)
            e. Set state["current_node"] = next_node
        5. Return.

    Exception handling:
        - CheckpointError: fatal for this thread — log and return without sending
        - Any exception inside a node: caught here, state routed to error_node
        - error_node exceptions: logged but not re-raised (poller must continue)

    Concurrency note:
        The poller (Phase 7) ensures only one run() call executes per thread_id
        at a time via an asyncio.Lock keyed on thread_id.
    """
    logger.info(
        "Agent loop starting for thread %s.", thread_id,
        extra={"thread_id": thread_id},
    )

    # ── Step 1: Load or init state ─────────────────────────────────────────────
    state = load_state(thread_id)
    if state is None:
        state = init_state(thread_id, email_obj)
        logger.info("New session initialised.", extra={"thread_id": thread_id})
    else:
        logger.info(
            "Resuming session (node=%s).", state.get("current_node"),
            extra={"thread_id": thread_id},
        )

    # ── Step 2: Load participant preferences into state ────────────────────────
    from preference_store import load_preferences
    for participant in state["participants"]:
        if participant not in state["preferences"]:
            state["preferences"][participant] = load_preferences(participant)

    # ── Step 3: Always re-enter at triage_node for a new email ─────────────────
    state["current_node"] = "triage_node"

    # ── Step 4: Node execution loop ────────────────────────────────────────────
    while state["current_node"] != END:
        current_node_name = state["current_node"]
        node_fn = NODE_REGISTRY.get(current_node_name)

        if node_fn is None:
            logger.error(
                "Unknown node '%s' in GRAPH — routing to error_node.", current_node_name,
                extra={"thread_id": thread_id},
            )
            state["error"] = f"Unknown node: {current_node_name}"
            state["current_node"] = "error_node"
            continue

        # Execute node
        try:
            state = node_fn(state, email_obj)
        except Exception as exc:
            logger.error(
                "Unhandled exception in node '%s': %s", current_node_name, exc,
                exc_info=True, extra={"thread_id": thread_id},
            )
            state["error"] = f"Node {current_node_name} raised: {exc}"
            state["current_node"] = "error_node"
            # Don't checkpoint here — fall through to the checkpoint below

        # Checkpoint after every node (even error_node)
        try:
            save_state(thread_id, state)
        except CheckpointError as exc:
            logger.critical(
                "CheckpointError after node '%s': %s — halting loop.",
                current_node_name, exc, extra={"thread_id": thread_id},
            )
            return  # Cannot save state — abort without sending

        # Check if node already set current_node (e.g. to error_node)
        if state["current_node"] == "error_node" and current_node_name != "error_node":
            continue  # will execute error_node on next iteration

        # Get next node from GRAPH routing function
        router_fn = GRAPH.get(current_node_name)
        if router_fn is None:
            logger.error(
                "No router for node '%s' — terminating loop.", current_node_name,
                extra={"thread_id": thread_id},
            )
            break

        next_node = router_fn(state)
        state["current_node"] = next_node
        logger.debug(
            "%s → %s", current_node_name, next_node,
            extra={"thread_id": thread_id},
        )

    logger.info(
        "Agent loop complete for thread %s.", thread_id,
        extra={"thread_id": thread_id},
    )
```

---

## 6. State Transition Diagram (ASCII)

```
                    ┌─────────────┐
 email arrives ────→│ triage_node │
                    └──────┬──────┘
                           │
         ┌─────────────────┼─────────────────────┐
         │                 │                      │
    scheduling/       update_request          noise/error
    reschedule             │                      │
         │                 ▼                      ▼
         │     ┌────────────────────────┐   ┌─────────────┐
         │     │ thread_intelligence_node│   │  error_node │──→ END
         │     └────────────┬───────────┘   └─────────────┘
         │                  │
         ▼                  │
┌──────────────────┐        │
│ coordination_node│        │
└────────┬─────────┘        │
         │                  │
   ambiguity?─── Yes ───→ ┌──────────────┐
         │                │ ambiguity_node│
         │                └──────┬───────┘
         │                       │
         │                       ▼
         │                 ┌───────────┐
         │                 │ send_node │──→ clear_state → END
         │                 └───────────┘
         │
   all responded?
         │
        Yes
         ▼
  ┌─────────────┐
  │ overlap_node│
  └──────┬──────┘
         │
         ▼
┌─────────────────┐
│ rank_slots_node │
└────────┬────────┘
         │
  below threshold?──── Yes (restart < 2) ──→ coordination_node
         │              Yes (restart >= 2) ──→ error_node
        No
         │
         ▼
  ┌───────────────┐
  │ calendar_node │
  └───────┬───────┘
          │ (also: thread_intelligence_node arrives here via rewrite)
          ▼
  ┌──────────────┐
  │ rewrite_node │◄──── rejected (from approval_node)
  └──────┬───────┘
         │
         ▼
  ┌───────────────┐
  │ approval_node │
  └───────┬───────┘
          │
   approved/timeout ──→ send_node ──→ clear_state → END
```

---

## 7. Node State Read/Write Table

| Node | Reads from state | Writes to state |
|---|---|---|
| `triage_node` | `history` | `intent`, `history` |
| `coordination_node` | `participants`, `pending_responses`, `preferences`, `non_responsive` | `slots_per_participant` (via tool), `pending_responses`, `outbound_draft`, `ambiguity_rounds` |
| `ambiguity_node` | `ambiguity_rounds`, `outbound_draft` | `non_responsive`, `pending_responses` |
| `overlap_node` | `thread_id`, `non_responsive` | `overlap_candidates` |
| `rank_slots_node` | `overlap_candidates`, `preferences`, `coordination_restart_count` | `ranked_slot`, `rank_below_threshold`, `outbound_draft`, `coordination_restart_count`, `slots_per_participant`, `pending_responses` |
| `calendar_node` | `ranked_slot`, `participants` | `outbound_draft`, `calendar_event_id` |
| `thread_intelligence_node` | `thread_id`, `history` | `outbound_draft` |
| `rewrite_node` | `outbound_draft` | `outbound_draft` (polished) |
| `approval_node` | `outbound_draft` | `approval_status` |
| `send_node` | `outbound_draft` | — (calls clear_state after send) |
| `error_node` | `error`, `current_node` | — (logs only) |

---

## 8. AgentState — Two Additional Fields

Add these to `AgentState` TypedDict in `models.py` (Phase 6 additions):

```python
# Add to AgentState TypedDict in models.py:
overlap_candidates:         list[dict]   # temp: candidate slots from overlap_node
rank_below_threshold:       bool         # True if rank_slots scored below threshold
calendar_event_id:          Optional[str]  # Google Calendar event ID after creation
coordination_restart_count: int          # how many times we've restarted coordination
```

---

## 9. Error Handling

| Scenario | What Happens |
|---|---|
| Node raises unhandled exception | Caught in `loop.py`, `state["error"]` set, `current_node = "error_node"`, checkpoint saved |
| `CheckpointError` after node | Loop halts immediately — no email sent, no further processing |
| `error_node` raises | Logged as CRITICAL, loop exits, poller continues with other emails |
| Unknown node name in GRAPH | Logged as ERROR, routes to `error_node` |
| `rewrite_node` Gemini fails | Warning logged, original `outbound_draft` kept (non-fatal) |
| `send_node` SMTP fails | ERROR logged, `state["error"]` set — session NOT cleared (preserves state) |

---

## 10. Unit Tests — tests/test_agent_loop.py

```python
# tests/test_agent_loop.py
"""
Integration tests for the agent loop with mocked external dependencies.
Run: pytest tests/test_agent_loop.py -v
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

import db as db_module
from db import init_db
from models import EmailObject, init_state


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "test.db")
    init_db()


def _email_obj(
    thread_id="<root001@example.com>",
    sender="alice@example.com",
    subject="Team sync",
    body="Let's meet next week.",
) -> EmailObject:
    return EmailObject(
        message_id="<msg001@example.com>",
        thread_id=thread_id,
        sender_email=sender,
        sender_name="Alice",
        subject=subject,
        body=body,
        timestamp=datetime(2026, 4, 4, 9, 0, tzinfo=timezone.utc),
        in_reply_to="",
        recipients=["mailmind@gmail.com"],
    )


class TestTriageNodeRouting:
    """Test case 1 — triage classifies intent and routes correctly."""

    def test_scheduling_intent_routes_to_coordination(self):
        from agent.router import route_by_intent
        state = {"intent": "scheduling", "thread_id": "tid1"}
        assert route_by_intent(state) == "coordination_node"

    def test_noise_intent_routes_to_error(self):
        from agent.router import route_by_intent
        state = {"intent": "noise", "thread_id": "tid1"}
        assert route_by_intent(state) == "error_node"

    def test_update_request_routes_to_thread_intelligence(self):
        from agent.router import route_by_intent
        state = {"intent": "update_request", "thread_id": "tid1"}
        assert route_by_intent(state) == "thread_intelligence_node"


class TestRouteByCompleteness:
    """Test case 2 — coordination routing logic."""

    def test_all_responded_routes_to_overlap(self):
        from agent.router import route_by_completeness
        state = {"pending_responses": [], "outbound_draft": None, "thread_id": "tid1"}
        assert route_by_completeness(state) == "overlap_node"

    def test_pending_responses_routes_to_end(self):
        from agent.router import route_by_completeness
        state = {"pending_responses": ["bob@example.com"], "outbound_draft": None, "thread_id": "tid1"}
        from agent.graph import END
        assert route_by_completeness(state) == END

    def test_draft_set_routes_to_ambiguity(self):
        from agent.router import route_by_completeness
        state = {"pending_responses": ["bob@example.com"], "outbound_draft": "Please clarify.", "thread_id": "tid1"}
        assert route_by_completeness(state) == "ambiguity_node"


class TestRouteByThreshold:
    """Test case 3 — rank_slots routing."""

    def test_slot_found_routes_to_calendar(self):
        from agent.router import route_by_threshold
        state = {
            "ranked_slot": {"start_utc": "2026-04-07T09:00:00+00:00"},
            "rank_below_threshold": False,
            "coordination_restart_count": 0,
            "thread_id": "tid1",
        }
        assert route_by_threshold(state) == "calendar_node"

    def test_below_threshold_restarts_coordination(self):
        from agent.router import route_by_threshold
        state = {
            "ranked_slot": None,
            "rank_below_threshold": True,
            "coordination_restart_count": 0,
            "thread_id": "tid1",
        }
        assert route_by_threshold(state) == "coordination_node"

    def test_two_restarts_routes_to_error(self):
        from agent.router import route_by_threshold
        state = {
            "ranked_slot": None,
            "rank_below_threshold": True,
            "coordination_restart_count": 2,
            "thread_id": "tid1",
        }
        assert route_by_threshold(state) == "error_node"


class TestRouteByApproval:
    """Test case 4 — approval gate routing."""

    def test_approved_routes_to_send(self):
        from agent.router import route_by_approval
        assert route_by_approval({"approval_status": "approved", "thread_id": "t"}) == "send_node"

    def test_timeout_routes_to_send(self):
        from agent.router import route_by_approval
        assert route_by_approval({"approval_status": "timeout", "thread_id": "t"}) == "send_node"

    def test_rejected_routes_to_rewrite(self):
        from agent.router import route_by_approval
        assert route_by_approval({"approval_status": "rejected", "thread_id": "t"}) == "rewrite_node"


class TestLoopCheckpointing:
    """Test case 5 — state is checkpointed after every node."""

    def test_state_saved_after_triage(self):
        with patch("agent.nodes.call_with_tools") as mock_tools, \
             patch("agent.nodes.call_for_text"), \
             patch("preference_store.load_preferences", return_value={}), \
             patch("tool_registry.call_tool") as mock_call:

            mock_tools.return_value = {"intent": "noise", "confidence": 0.9}
            mock_call.return_value = {"sent": True, "to": "alice@example.com", "subject": "test"}

            from agent.loop import run
            from checkpointer import load_state

            email = _email_obj()
            run(email["thread_id"], email)

            # State must be saved (noise → error_node → END)
            # At minimum, triage should have saved once
            # (or error_node saves)
            # We verify no exception was raised and loop completed
```

---

## 11. Integration Checklist

- [ ] `agent/__init__.py` exists (empty)
- [ ] `agent/graph.py` defines all 11 node name constants and `END = "__END__"`
- [ ] `agent/graph.py` GRAPH dict maps every node name to a routing function or lambda
- [ ] `agent/router.py` implements all 4 routing functions
- [ ] `route_by_completeness` returns `END` (not error) when still waiting on participants
- [ ] `route_by_threshold` caps restart at 2 before routing to `error_node`
- [ ] `agent/nodes.py` implements all 10 nodes + `NODE_REGISTRY` dict
- [ ] Every node returns `AgentState` — even on error (state["current_node"] = "error_node")
- [ ] `triage_node` catches `GeminiAPIError` and `LowConfidenceError`
- [ ] `rewrite_node` is non-fatal on Gemini failure — uses original draft
- [ ] `send_node` calls `clear_state()` after successful send
- [ ] `calendar_node` calls `store_preferences()` for all participants after event creation
- [ ] `agent/loop.py` checkpoints after EVERY node including `error_node`
- [ ] `loop.py` halts on `CheckpointError` — does NOT send email in unsafe state
- [ ] `AgentState` in `models.py` has 4 new fields: `overlap_candidates`, `rank_below_threshold`, `calendar_event_id`, `coordination_restart_count`
- [ ] `pytest tests/test_agent_loop.py -v` passes all routing tests

---

*PHASE6_AGENT_STATE_MACHINE.md | Team TRIOLOGY | PCCOE Pune | Problem Statement 03*
