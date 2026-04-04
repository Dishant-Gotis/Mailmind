"""
Thread-level intelligence tools for summaries, status, and cancellation detection.
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from checkpointer import load_state
from logger import get_logger
from preference_store import get_historical_slots
from prompt_builder import build_summarise_prompt
from tool_caller import call_for_text

logger = get_logger(__name__)


def summarise_thread(thread_id: str) -> dict[str, Any]:
    """
    Summarise thread history using the existing text-only LLM call flow.
    """
    state = load_state(thread_id)
    if state is None:
        return {"summary": "No thread history found.", "thread_id": thread_id}

    history = state.get("history", [])
    if not history:
        return {"summary": "Thread has no recorded history yet.", "thread_id": thread_id}

    history_text = "\n\n".join(
        f"[{entry.get('role', 'unknown').upper()}]: {entry.get('content', '')}"
        for entry in history
    )
    messages = build_summarise_prompt(history_text)
    summary = call_for_text(messages=messages, thread_id=thread_id, temperature=0.4)
    return {"summary": summary, "thread_id": thread_id}


def get_scheduling_status(thread_id: str) -> dict[str, Any]:
    """
    Return an at-a-glance state summary for status requests.
    """
    state = load_state(thread_id)
    if state is None:
        return {
            "thread_id": thread_id,
            "intent": "unknown",
            "participants": [],
            "pending_responses": [],
            "has_ranked_slot": False,
            "approval_status": "none",
            "current_node": "",
        }

    return {
        "thread_id": thread_id,
        "intent": state.get("intent", "unknown"),
        "participants": state.get("participants", []),
        "pending_responses": state.get("pending_responses", []),
        "has_ranked_slot": state.get("ranked_slot") is not None,
        "approval_status": state.get("approval_status", "none"),
        "current_node": state.get("current_node", ""),
    }


def detect_cancellation(body: str) -> dict[str, bool]:
    """
    Detect cancellation intent with deterministic phrase matching.
    """
    cancellation_patterns = [
        r"\bcancel\b",
        r"\bcancelling\b",
        r"\bcanceled\b",
        r"\bcancelled\b",
        r"\bno longer\b",
        r"\bcall off\b",
        r"\bcalled off\b",
        r"\bwon't be able\b",
        r"\bcannot make\b",
        r"\bnot going to work\b",
        r"\bscrap(ping)?\b",
    ]
    for pattern in cancellation_patterns:
        if re.search(pattern, body, flags=re.IGNORECASE):
            return {"is_cancellation": True}
    return {"is_cancellation": False}


def suggest_optimal_time(email: str) -> dict[str, Any]:
    """
    Derive preferred hour/day buckets from stored historical accepted slots.
    """
    slots = get_historical_slots(email)
    if not slots:
        return {
            "email": email,
            "preferred_hour_buckets": [],
            "preferred_days": [],
            "sample_size": 0,
        }

    hour_counter: Counter[int] = Counter()
    day_counter: Counter[str] = Counter()

    for slot in slots:
        start_val = slot.get("start_utc")
        if not start_val:
            continue

        if isinstance(start_val, datetime):
            start_dt = start_val
        else:
            try:
                start_dt = datetime.fromisoformat(str(start_val))
            except ValueError:
                continue

        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=timezone.utc)
        start_dt = start_dt.astimezone(timezone.utc)

        hour_counter[start_dt.hour] += 1
        day_counter[start_dt.strftime("%A")] += 1

    return {
        "email": email,
        "preferred_hour_buckets": [hour for hour, _ in hour_counter.most_common(3)],
        "preferred_days": [day for day, _ in day_counter.most_common(3)],
        "sample_size": len(slots),
    }
