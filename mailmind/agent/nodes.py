"""
Agent node implementations for the MailMind state machine.

Node calling convention
-----------------------
Every node receives (state, email_obj) and returns the mutated state.
Routing decisions are made by agent/loop.py using agent/graph.py.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from checkpointer import clear_state
from exceptions import LowConfidenceError, OpenRouterAPIError, ToolNotFoundError
from logger import get_logger
from models import AgentState, EmailObject
from preference_store import load_preferences, store_preferences
from prompt_builder import (
    append_to_history,
    build_ambiguity_prompt,
    build_coordination_prompt,
    build_rewrite_prompt,
    build_triage_prompt,
)
from tool_caller import call_for_text, call_with_tools
from tool_registry import ALL_TOOL_SCHEMAS, call_tool

logger = get_logger(__name__)

MAX_COORDINATION_RESTARTS = 2
MAX_CLARIFICATION_ROUNDS = 2
VALID_APPROVAL_STATUSES = {"approved", "rejected", "timeout"}


def _normalise_email(email: str) -> str:
    return email.lower().strip()


def _slot_start_iso(slot: dict) -> str | None:
    value = slot.get("start_utc")
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str):
        return value
    return None


def _build_pending_responses(state: AgentState, sender: str) -> list[str]:
    non_responsive = {_normalise_email(e) for e in state.get("non_responsive", [])}
    participants = {_normalise_email(e) for e in state.get("participants", [])}
    participants.discard(sender)

    try:
        from config import config

        participants.discard(_normalise_email(config.gmail_address))
    except Exception:
        pass

    return sorted([email for email in participants if email not in non_responsive])


def request_approval(draft: str, thread_id: str) -> str:
    """
    Phase 6 stub: approval channel is not integrated yet.
    """
    logger.warning(
        "request_approval not integrated yet; auto-approving draft.",
        extra={"thread_id": thread_id},
    )
    _ = draft
    return "approved"


def send_alert(message: str) -> None:
    """
    Phase 6 stub: alerting channel is not integrated yet.
    """
    logger.error("ALERT: %s", message)


def _is_affirmative_without_time(text: str) -> bool:
    """
    Detect short affirmative replies that imply agreement but omit a concrete time.
    """
    # Only inspect fresh reply content, not quoted thread tails.
    fresh_text = _extract_fresh_reply_text(text)
    lowered = fresh_text.lower().strip()
    affirmative_patterns = [
        r"\byes\b",
        r"\bworks for me\b",
        r"\bi am available\b",
        r"\bavailable\b",
        r"\bsounds good\b",
        r"\bok\b",
        r"\bagreed\b",
    ]
    if not any(re.search(p, lowered) for p in affirmative_patterns):
        return False

    has_time_markers = bool(
        re.search(r"\b\d{1,2}(:\d{2})?\s*(am|pm|a\.m\.|p\.m\.|utc|ist|pst|est)\b", lowered)
        or re.search(
            r"\b(tomorrow|today|monday|tuesday|wednesday|thursday|friday|saturday|sunday|\d{1,2}\s+\w+)\b",
            lowered,
        )
    )
    return not has_time_markers


def _extract_fresh_reply_text(text: str) -> str:
    """
    Return only the newest reply content, excluding quoted thread tails.
    """
    fresh_text = text.split("\nOn ")[0]
    fresh_text = fresh_text.split("\n>")[0]
    return fresh_text.strip()


def _extract_quoted_reply_text(text: str) -> str:
    """
    Return quoted thread content with quote markers removed.
    """
    marker = "\nOn "
    idx = text.find(marker)
    if idx == -1:
        return ""

    quoted_part = text[idx + 1 :].strip()
    cleaned_lines: list[str] = []
    for line in quoted_part.splitlines():
        cleaned_lines.append(re.sub(r"^\s*>\s?", "", line))
    return "\n".join(cleaned_lines).strip()


def _inherit_slots_from_thread_context(state: AgentState, sender: str) -> list[dict]:
    """
    Copy latest known slots from another participant onto the sender.
    """
    sender_norm = _normalise_email(sender)
    slots_per_participant = state.get("slots_per_participant", {})

    for participant, slots in slots_per_participant.items():
        participant_norm = _normalise_email(participant)
        if participant_norm == sender_norm:
            continue
        if not slots:
            continue

        inherited = []
        for slot in slots:
            copied = dict(slot)
            copied["participant"] = sender_norm
            inherited.append(copied)
        return inherited

    return []


def _build_llm_clarification(email_obj: EmailObject, thread_id: str, state: AgentState | None = None) -> str:
    """
    Generate a concise clarification question using LLM with a safe fallback.
    """
    default_question = (
        "I could not confidently understand your scheduling intent. "
        "Could you share 2-3 exact date/time windows in your timezone? "
        "Example: Monday 07 Apr 10:00-11:00 IST, Tuesday 08 Apr 14:00-15:00 IST."
    )

    try:
        user_text = email_obj.get("body", "").strip()
        history = []
        if state:
            history = state.get("history", [])[-4:]
        history_text = "\n".join(
            [f"{h.get('role', 'unknown')}: {h.get('content', '')}" for h in history]
        )
        prompt = [
            {
                "role": "system",
                "content": (
                    "You are an email scheduling assistant. "
                    "Write ONE polite, short clarification question asking for specific availability. "
                    "Do not include markdown. Do not include more than 2 sentences."
                ),
            },
            {
                "role": "user",
                "content": (
                    "The user message was unclear for scheduling extraction:\n\n"
                    f"{user_text}\n\n"
                    "Recent thread context:\n"
                    f"{history_text}\n\n"
                    "Ask them to provide concrete date/time windows with timezone."
                ),
            },
        ]
        text = call_for_text(prompt, thread_id=thread_id, temperature=0.2, max_tokens=120).strip()
        return text or default_question
    except Exception:
        return default_question


# Node 1: triage_node

def triage_node(state: AgentState, email_obj: EmailObject) -> AgentState:
    """
    Classify inbound intent using model tool-calling.
    """
    thread_id = state["thread_id"]
    try:
        messages = build_triage_prompt(email_obj, state)
        schema = [s for s in ALL_TOOL_SCHEMAS if s["function"]["name"] == "classify"]
        result = call_with_tools(messages, schema, thread_id=thread_id, temperature=0.2)

        state["intent"] = result.get("intent", "noise")
        if state["intent"] == "reschedule":
            state["slots_per_participant"] = {}
            state["ranked_slot"] = None
            state["rank_below_threshold"] = False
            state["pending_responses"] = list(state.get("participants", []))
            state["overlap_candidates"] = []
            state["coordination_restart_count"] = 0
        append_to_history(state, "user", email_obj.get("body", ""))
        append_to_history(state, "assistant", f"Intent classified: {state['intent']}")

        logger.info("triage_node: intent=%s", state["intent"], extra={"thread_id": thread_id})
    except LowConfidenceError as exc:
        # Graceful fallback: do not hard-fail low-confidence classification.
        # Route into coordination with an ambiguity flag so we can ask a clear follow-up.
        state["intent"] = "scheduling"
        state["triage_ambiguous"] = True
        append_to_history(state, "user", email_obj.get("body", ""))
        append_to_history(state, "assistant", "Low-confidence intent; requesting clarification.")
        logger.warning("triage_node low-confidence fallback: %s", exc, extra={"thread_id": thread_id})
    except (OpenRouterAPIError, ToolNotFoundError) as exc:
        logger.error("triage_node error: %s", exc, extra={"thread_id": thread_id})
        state["error"] = str(exc)
        state["current_node"] = "error_node"
    return state


# Node 2: coordination_node

def coordination_node(state: AgentState, email_obj: EmailObject) -> AgentState:
    """
    Parse availability, persist participant slots, and detect ambiguity.
    """
    thread_id = state["thread_id"]
    sender = _normalise_email(email_obj["sender_email"])

    state.setdefault("slots_per_participant", {})
    state.setdefault("pending_responses", [])
    state.setdefault("ambiguity_rounds", {})
    state.setdefault("preferences", {})

    if state.pop("triage_ambiguous", False):
        state["outbound_draft"] = _build_llm_clarification(email_obj, thread_id, state)
        logger.info(
            "coordination_node: triage ambiguity fallback triggered for %s",
            sender,
            extra={"thread_id": thread_id},
        )
        return state

    if not state["pending_responses"]:
        state["pending_responses"] = _build_pending_responses(state, sender)

    sender_tz = state["preferences"].get(sender, {}).get("timezone", "UTC")
    body_text = email_obj.get("body", "")
    fresh_body_text = _extract_fresh_reply_text(body_text)

    try:
        ambiguity_schema = [
            s for s in ALL_TOOL_SCHEMAS if s["function"]["name"] == "detect_ambiguity"
        ]
        ambiguity_msgs = build_ambiguity_prompt(email_obj, state)
        amb_result = call_with_tools(
            ambiguity_msgs,
            ambiguity_schema,
            thread_id=thread_id,
            temperature=0.2,
        )

        if amb_result.get("is_ambiguous"):
            if _is_affirmative_without_time(body_text):
                inherited_slots = _inherit_slots_from_thread_context(state, sender)
                if not inherited_slots:
                    quoted_text = _extract_quoted_reply_text(body_text)
                    if quoted_text:
                        quoted_parse = call_tool(
                            "parse_availability",
                            {"text": quoted_text, "sender_tz": sender_tz},
                        )
                        inherited_slots = quoted_parse.get("slots", [])
                        for slot in inherited_slots:
                            slot["participant"] = sender
                if inherited_slots:
                    call_tool(
                        "track_participant_slots",
                        {
                            "thread_id": thread_id,
                            "email": sender,
                            "slots": inherited_slots,
                        },
                    )

                    existing = list(state["slots_per_participant"].get(sender, []))
                    existing.extend(inherited_slots)
                    state["slots_per_participant"][sender] = existing

                    if sender in state["pending_responses"]:
                        state["pending_responses"].remove(sender)

                    state["outbound_draft"] = None
                    append_to_history(
                        state,
                        "assistant",
                        f"Affirmative reply from {sender}; inherited {len(inherited_slots)} slot(s) from thread context.",
                    )
                    logger.info(
                        "coordination_node: affirmative from %s; inherited %d slot(s). Pending=%s",
                        sender,
                        len(inherited_slots),
                        state["pending_responses"],
                        extra={"thread_id": thread_id},
                    )
                    return state

            rounds = state["ambiguity_rounds"].get(sender, 0)
            state["ambiguity_rounds"][sender] = rounds + 1
            state["outbound_draft"] = amb_result.get("question") or _build_llm_clarification(
                email_obj,
                thread_id,
                state,
            )
            logger.info(
                "coordination_node: ambiguity detected for %s (round %d)",
                sender,
                rounds + 1,
                extra={"thread_id": thread_id},
            )
            return state

        _ = build_coordination_prompt(email_obj, state)
        avail_result = call_tool(
            "parse_availability",
            {"text": fresh_body_text, "sender_tz": sender_tz},
        )
        slots = avail_result.get("slots", [])

        for slot in slots:
            slot["participant"] = sender

        call_tool(
            "track_participant_slots",
            {
                "thread_id": thread_id,
                "email": sender,
                "slots": slots,
            },
        )

        existing = list(state["slots_per_participant"].get(sender, []))
        existing.extend(slots)
        state["slots_per_participant"][sender] = existing

        append_to_history(state, "user", email_obj.get("body", ""))

        if not slots:
            if _is_affirmative_without_time(body_text):
                inherited_slots = _inherit_slots_from_thread_context(state, sender)
                if not inherited_slots:
                    quoted_text = _extract_quoted_reply_text(body_text)
                    if quoted_text:
                        quoted_parse = call_tool(
                            "parse_availability",
                            {"text": quoted_text, "sender_tz": sender_tz},
                        )
                        inherited_slots = quoted_parse.get("slots", [])
                        for slot in inherited_slots:
                            slot["participant"] = sender
                if inherited_slots:
                    call_tool(
                        "track_participant_slots",
                        {
                            "thread_id": thread_id,
                            "email": sender,
                            "slots": inherited_slots,
                        },
                    )

                    existing = list(state["slots_per_participant"].get(sender, []))
                    existing.extend(inherited_slots)
                    state["slots_per_participant"][sender] = existing

                    if sender in state["pending_responses"]:
                        state["pending_responses"].remove(sender)

                    state["outbound_draft"] = None
                    append_to_history(
                        state,
                        "assistant",
                        f"Affirmative fallback from {sender}; inherited {len(inherited_slots)} slot(s).",
                    )
                    logger.info(
                        "coordination_node: affirmative fallback from %s; inherited %d slot(s). Pending=%s",
                        sender,
                        len(inherited_slots),
                        state["pending_responses"],
                        extra={"thread_id": thread_id},
                    )
                    return state

            if sender not in state["pending_responses"]:
                state["pending_responses"].append(sender)
            state["outbound_draft"] = _build_llm_clarification(email_obj, thread_id, state)
            append_to_history(
                state,
                "assistant",
                "No availability could be parsed; requesting clarification.",
            )
            logger.info(
                "coordination_node: no availability parsed from %s. Pending=%s",
                sender,
                state["pending_responses"],
                extra={"thread_id": thread_id},
            )
        else:
            if sender in state["pending_responses"]:
                state["pending_responses"].remove(sender)

            state["outbound_draft"] = None
            append_to_history(state, "assistant", f"Parsed {len(slots)} slot(s) from {sender}.")

            logger.info(
                "coordination_node: %d slot(s) parsed from %s. Pending=%s",
                len(slots),
                sender,
                state["pending_responses"],
                extra={"thread_id": thread_id},
            )
    except Exception as exc:
        logger.error("coordination_node error: %s", exc, extra={"thread_id": thread_id})
        state["error"] = str(exc)
        state["current_node"] = "error_node"
    return state


# Node 3: ambiguity_node

def ambiguity_node(state: AgentState, email_obj: EmailObject) -> AgentState:
    """
    Handle repeated ambiguity; mark participant non-responsive after retries.
    """
    thread_id = state["thread_id"]
    sender = _normalise_email(email_obj["sender_email"])
    if not state.get("pending_responses"):
        # Direct-email case can legitimately have no pending participants while
        # still requiring a clarification draft to be sent back to the sender.
        if state.get("outbound_draft"):
            logger.info(
                "ambiguity_node: no pending responses; preserving clarification draft for sender.",
                extra={"thread_id": thread_id},
            )
        else:
            logger.info(
                "ambiguity_node: no pending responses and no draft present.",
                extra={"thread_id": thread_id},
            )
        return state

    rounds = state.get("ambiguity_rounds", {}).get(sender, 0)

    if rounds >= MAX_CLARIFICATION_ROUNDS:
        state.setdefault("non_responsive", [])
        if sender not in state["non_responsive"]:
            state["non_responsive"].append(sender)

        if sender in state.get("pending_responses", []):
            state["pending_responses"].remove(sender)

        state["outbound_draft"] = None
        logger.warning(
            "ambiguity_node: %s marked non-responsive after %d rounds.",
            sender,
            rounds,
            extra={"thread_id": thread_id},
        )

    return state


# Node 4: overlap_node

def overlap_node(state: AgentState, email_obj: EmailObject) -> AgentState:
    """
    Compute overlap candidates from stored participant slots.
    """
    _ = email_obj
    thread_id = state["thread_id"]
    try:
        result = call_tool("find_overlap", {"thread_id": thread_id})
        state["overlap_candidates"] = result.get("candidates", [])
        logger.info(
            "overlap_node: %d candidate(s) found.",
            len(state["overlap_candidates"]),
            extra={"thread_id": thread_id},
        )
    except Exception as exc:
        logger.error("overlap_node error: %s", exc, extra={"thread_id": thread_id})
        state["error"] = str(exc)
        state["current_node"] = "error_node"
    return state


# Node 5: rank_slots_node

def rank_slots_node(state: AgentState, email_obj: EmailObject) -> AgentState:
    """
    Score overlap candidates and prepare either ranked slot or restart draft.
    """
    _ = email_obj
    thread_id = state["thread_id"]
    candidates = state.get("overlap_candidates", [])

    enriched_prefs: dict[str, dict] = {}
    slots_per_participant = state.get("slots_per_participant", {})

    for email in state.get("participants", []):
        email_lc = _normalise_email(email)
        stored = load_preferences(email_lc)
        enriched_prefs[email_lc] = {
            "email": email_lc,
            "preferred_hours_start": stored.get("preferred_hours_start", 9),
            "preferred_hours_end": stored.get("preferred_hours_end", 17),
            "blocked_days": stored.get("blocked_days", []),
            "vip": stored.get("vip", False),
            "timezone": stored.get("timezone", "UTC"),
            "slots": slots_per_participant.get(email_lc, []),
            "preferred_hour_buckets": stored.get("preferred_hour_buckets", []),
            "preferred_days": stored.get("preferred_days", []),
        }

    try:
        result = call_tool(
            "rank_slots",
            {
                "candidate_slots": candidates,
                "preferences": enriched_prefs,
            },
        )

        state["ranked_slot"] = result.get("ranked_slot")
        state["rank_below_threshold"] = bool(result.get("below_threshold", True))

        if state["rank_below_threshold"]:
            state["coordination_restart_count"] = state.get("coordination_restart_count", 0) + 1
            state["outbound_draft"] = (
                "Hi all,\n\n"
                "We were not able to find a slot that works for enough participants.\n"
                "Could everyone share 2-3 additional availability windows?\n\n"
                "Example:\n"
                "  - Monday 07 Apr 10:00-11:00 IST\n"
                "  - Tuesday 08 Apr 15:00-16:00 IST\n\n"
                "Thank you,\n"
                "MailMind"
            )
            state["slots_per_participant"] = {}
            state["overlap_candidates"] = []
            non_responsive = {_normalise_email(e) for e in state.get("non_responsive", [])}
            bot_email = ""
            try:
                from config import config

                bot_email = _normalise_email(config.gmail_address)
            except Exception:
                bot_email = ""
            state["pending_responses"] = [
                _normalise_email(p)
                for p in state.get("participants", [])
                if _normalise_email(p) not in non_responsive and _normalise_email(p) != bot_email
            ]
            logger.warning(
                "rank_slots_node: score below threshold, restart_count=%d",
                state["coordination_restart_count"],
                extra={"thread_id": thread_id},
            )
        else:
            state["outbound_draft"] = None
            logger.info(
                "rank_slots_node: selected slot score=%.4f reason=%s",
                float(result.get("score", 0.0)),
                result.get("reason", ""),
                extra={"thread_id": thread_id},
            )

        if state.get("coordination_restart_count", 0) > MAX_COORDINATION_RESTARTS:
            state["error"] = (
                "rank_slots_node: No suitable slot found after max coordination restarts."
            )
            state["current_node"] = "error_node"
    except Exception as exc:
        logger.error("rank_slots_node error: %s", exc, extra={"thread_id": thread_id})
        state["error"] = str(exc)
        state["current_node"] = "error_node"
    return state


# Node 6: calendar_node

def calendar_node(state: AgentState, email_obj: EmailObject) -> AgentState:
    """
    Create a calendar event for the selected ranked slot and draft confirmation.
    """
    thread_id = state["thread_id"]
    slot = state.get("ranked_slot")

    if not slot:
        state["error"] = "calendar_node called without ranked_slot"
        state["current_node"] = "error_node"
        return state

    start_utc = _slot_start_iso(slot)
    if not start_utc:
        state["error"] = "calendar_node received invalid slot format"
        state["current_node"] = "error_node"
        return state

    try:
        from config import config

        start_dt = datetime.fromisoformat(start_utc)
        end_dt = start_dt + timedelta(minutes=config.meeting_duration_minutes)
        end_utc = end_dt.isoformat()

        title = email_obj.get("subject") or "Meeting via MailMind"
        participants = [_normalise_email(p) for p in state.get("participants", [])]

        dup_result = call_tool(
            "check_duplicate",
            {
                "title": title,
                "start_utc": start_utc,
                "participants": participants,
            },
        )

        if dup_result.get("duplicate"):
            state["calendar_event_id"] = dup_result.get("event_id")
            state["outbound_draft"] = (
                f"A meeting titled '{title}' at {start_utc} already exists. "
                "No duplicate event was created."
            )
            logger.info(
                "calendar_node: duplicate event found id=%s",
                dup_result.get("event_id"),
                extra={"thread_id": thread_id},
            )
        else:
            event_result = call_tool(
                "create_event",
                {
                    "title": title,
                    "start_utc": start_utc,
                    "end_utc": end_utc,
                    "participants": participants,
                    "description": f"Meeting coordinated by MailMind. Thread={thread_id}",
                },
            )

            event_id = event_result.get("event_id")
            state["calendar_event_id"] = event_id

            if event_id:
                call_tool("send_invite", {"event_id": event_id, "participants": participants})

            for participant in participants:
                store_preferences(participant, accepted_slot=slot)

            state["outbound_draft"] = (
                "Great news, your meeting has been scheduled.\n\n"
                f"Title: {title}\n"
                f"Time (UTC): {start_utc}\n"
                f"Participants: {', '.join(participants)}\n\n"
                f"Calendar link: {event_result.get('html_link', '')}"
            )
            logger.info(
                "calendar_node: event created id=%s",
                event_id,
                extra={"thread_id": thread_id},
            )
    except Exception as exc:
        logger.error("calendar_node error: %s", exc, extra={"thread_id": thread_id})
        state["error"] = str(exc)
        state["current_node"] = "error_node"
    return state


# Node 7: thread_intelligence_node

def thread_intelligence_node(state: AgentState, email_obj: EmailObject) -> AgentState:
    """
    Summarize thread status for update requests.
    """
    _ = email_obj
    thread_id = state["thread_id"]
    try:
        result = call_tool("summarise_thread", {"thread_id": thread_id})
        state["outbound_draft"] = result.get("summary", "No summary available.")
        logger.info("thread_intelligence_node: summary ready.", extra={"thread_id": thread_id})
    except Exception as exc:
        logger.error(
            "thread_intelligence_node error: %s",
            exc,
            extra={"thread_id": thread_id},
        )
        state["error"] = str(exc)
        state["current_node"] = "error_node"
    return state


# Node 8: rewrite_node

def rewrite_node(state: AgentState, email_obj: EmailObject) -> AgentState:
    """
    Polish outbound draft tone. Non-fatal if model call fails.
    """
    _ = email_obj
    thread_id = state["thread_id"]
    draft = state.get("outbound_draft", "")
    if not draft:
        state["error"] = "rewrite_node called with empty outbound_draft"
        state["current_node"] = "error_node"
        return state

    try:
        messages = build_rewrite_prompt(draft)
        polished = call_for_text(messages, thread_id=thread_id, temperature=0.7).strip()
        if polished:
            state["outbound_draft"] = polished
        logger.info("rewrite_node: draft polished.", extra={"thread_id": thread_id})
    except Exception as exc:
        logger.warning(
            "rewrite_node error (%s) - using unpolished draft.",
            exc,
            extra={"thread_id": thread_id},
        )
    return state


# Node 9: approval_node

def approval_node(state: AgentState, email_obj: EmailObject) -> AgentState:
    """
    Stub approval gate for Phase 6.
    """
    _ = email_obj
    thread_id = state["thread_id"]
    draft = state.get("outbound_draft", "")

    try:
        status = request_approval(draft, thread_id=thread_id)
        if status not in VALID_APPROVAL_STATUSES:
            status = "approved"
        state["approval_status"] = status
        logger.info("approval_node: status=%s", status, extra={"thread_id": thread_id})
    except Exception as exc:
        logger.error(
            "approval_node error: %s - using timeout fallback.",
            exc,
            extra={"thread_id": thread_id},
        )
        state["approval_status"] = "timeout"

    return state


# Node 10: send_node

def send_node(state: AgentState, email_obj: EmailObject) -> AgentState:
    """
    Send final outbound email and clear session on success.
    """
    thread_id = state["thread_id"]
    draft = state.get("outbound_draft", "")

    if not draft:
        logger.warning("send_node: no draft to send.", extra={"thread_id": thread_id})
        return state

    try:
        to = _normalise_email(email_obj.get("sender_email", ""))
        if not to:
            raise ValueError("send_node requires sender_email in email_obj")

        participants = [_normalise_email(p) for p in state.get("participants", [])]
        cc = sorted([p for p in set(participants) if p and p != to])

        in_reply_to = email_obj.get("message_id", "")
        references_parts = []
        if email_obj.get("in_reply_to", ""):
            references_parts.append(email_obj.get("in_reply_to", ""))
        if in_reply_to:
            references_parts.append(in_reply_to)
        references = " ".join(references_parts)

        call_tool(
            "send_reply",
            {
                "to": to,
                "subject": email_obj.get("subject", "Meeting update"),
                "body": draft,
                "thread_id": thread_id,
                "in_reply_to": in_reply_to,
                "references": references,
                "cc": cc,
            },
        )
        logger.info("send_node: email sent.", extra={"thread_id": thread_id})

        clear_state(thread_id)
    except Exception as exc:
        logger.error("send_node error: %s", exc, extra={"thread_id": thread_id})
        state["error"] = str(exc)
        state["current_node"] = "error_node"
    return state


# Node 11: error_node

def error_node(state: AgentState, email_obj: EmailObject) -> AgentState:
    """
    Terminal error logger node.
    """
    _ = email_obj
    thread_id = state["thread_id"]
    error_msg = state.get("error", "Unknown error")

    logger.error(
        "error_node: %s (at node=%s)",
        error_msg,
        state.get("current_node", ""),
        extra={"thread_id": thread_id},
    )

    try:
        send_alert(f"MailMind error in thread {thread_id}: {error_msg}")
    except Exception:
        logger.exception("error_node: alert dispatch failed.", extra={"thread_id": thread_id})

    return state


NODE_REGISTRY: dict[str, object] = {
    "triage_node": triage_node,
    "coordination_node": coordination_node,
    "ambiguity_node": ambiguity_node,
    "overlap_node": overlap_node,
    "rank_slots_node": rank_slots_node,
    "calendar_node": calendar_node,
    "thread_intelligence_node": thread_intelligence_node,
    "rewrite_node": rewrite_node,
    "approval_node": approval_node,
    "send_node": send_node,
    "error_node": error_node,
}
