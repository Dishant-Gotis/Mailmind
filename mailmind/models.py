from __future__ import annotations

from datetime import datetime
from typing import Optional, TypedDict


class EmailObject(TypedDict):
    """
    Normalised representation of a single inbound email.
    Produced by email_parser.py. Consumed by agent/loop.py run().
    """
    message_id: str
    thread_id: str
    sender_email: str
    sender_name: str
    subject: str
    body: str
    timestamp: datetime
    in_reply_to: str
    recipients: list[str]


class TimeSlot(TypedDict):
    """
    A single availability window for a participant, normalised to UTC.
    """
    start_utc: datetime
    end_utc: datetime
    participant: str
    raw_text: str
    timezone: str


class AgentState(TypedDict):
    """
    The complete persistent state of one agent session, keyed by thread_id.
    """
    thread_id: str
    intent: str
    participants: list[str]
    slots_per_participant: dict[str, list[dict]]
    pending_responses: list[str]
    ranked_slot: Optional[dict]
    outbound_draft: Optional[str]
    approval_status: str
    preferences: dict[str, dict]
    history: list[dict]
    current_node: str
    ambiguity_rounds: dict[str, int]
    non_responsive: list[str]
    overlap_candidates: list[dict]
    rank_below_threshold: bool
    calendar_event_id: Optional[str]
    coordination_restart_count: int
    error: Optional[str]
    created_at: str
    updated_at: str


class PreferenceProfile(TypedDict):
    """
    Per-participant preference payload consumed by rank_slots().
    """
    email: str
    preferred_hours_start: int
    preferred_hours_end: int
    blocked_days: list[str]
    vip: bool
    timezone: str
    slots: list[dict]
    preferred_hour_buckets: list[int]
    preferred_days: list[str]


def init_state(thread_id: str, email_obj: "EmailObject") -> AgentState:
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    return AgentState(
        thread_id=thread_id,
        intent="unknown",
        participants=list({email_obj["sender_email"]} | set(email_obj["recipients"])),
        slots_per_participant={},
        pending_responses=[],
        ranked_slot=None,
        outbound_draft=None,
        approval_status="none",
        preferences={},
        history=[],
        current_node="triage_node",
        ambiguity_rounds={},
        non_responsive=[],
        overlap_candidates=[],
        rank_below_threshold=False,
        calendar_event_id=None,
        coordination_restart_count=0,
        error=None,
        created_at=now,
        updated_at=now,
    )
