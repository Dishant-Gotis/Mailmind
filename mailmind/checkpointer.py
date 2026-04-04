"""
Save, load, and clear AgentState from SQLite sessions table.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from db import get_db
from exceptions import CheckpointError, SessionNotFoundError
from logger import get_logger
from models import AgentState

logger = get_logger(__name__)

DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S+00:00"


def save_state(thread_id: str, state: AgentState) -> None:
    try:
        now_utc = datetime.now(timezone.utc).strftime(DATETIME_FORMAT)
        state["updated_at"] = now_utc
        state_json = _serialise_state(state)

        with get_db() as conn:
            conn.execute(
                """
                INSERT INTO sessions (thread_id, state_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(thread_id) DO UPDATE SET
                    state_json = excluded.state_json,
                    updated_at = excluded.updated_at
                """,
                (thread_id, state_json, now_utc),
            )
    except Exception as exc:
        raise CheckpointError(
            f"Failed to save state for thread {thread_id}: {exc}"
        ) from exc


def load_state(thread_id: str) -> Optional[AgentState]:
    try:
        with get_db() as conn:
            row = conn.execute(
                "SELECT state_json FROM sessions WHERE thread_id = ?",
                (thread_id,),
            ).fetchone()

        if row is None:
            return None

        state = _deserialise_state(row["state_json"])
        return state

    except Exception as exc:
        raise CheckpointError(
            f"Failed to load state for thread {thread_id}: {exc}"
        ) from exc


def find_thread_by_any_ref(refs: list[str]) -> Optional[str]:
    if not refs:
        return None
    try:
        with get_db() as conn:
            # We fetch all active thread_ids and check if they match any ref
            # In a real system you'd want a separate table mapping msg_ids to thread_ids
            # but for this SQLite session check, we can check if the thread_id exactly matches a ref
            placeholders = ",".join(["?"] * len(refs))
            row = conn.execute(
                f"SELECT thread_id FROM sessions WHERE thread_id IN ({placeholders}) LIMIT 1",
                tuple(refs)
            ).fetchone()
            if row:
                return row["thread_id"]
        return None
    except Exception as exc:
        logger.error("Error finding thread by refs: %s", exc)
        return None


def clear_state(thread_id: str) -> None:
    try:
        with get_db() as conn:
            conn.execute(
                "DELETE FROM sessions WHERE thread_id = ?",
                (thread_id,),
            )
    except Exception as exc:
        raise CheckpointError(
            f"Failed to clear state for thread {thread_id}: {exc}"
        ) from exc


def _serialise_state(state: AgentState) -> str:
    def default_serialiser(obj):
        if isinstance(obj, datetime):
            if obj.tzinfo is not None:
                obj = obj.astimezone(timezone.utc)
            else:
                obj = obj.replace(tzinfo=timezone.utc)
            return obj.strftime(DATETIME_FORMAT)
        raise TypeError(f"Object of type {type(obj)} is not JSON serialisable")

    return json.dumps(state, default=default_serialiser, ensure_ascii=False)


def _deserialise_state(state_json: str) -> AgentState:
    state: dict = json.loads(state_json)

    for email, slots in state.get("slots_per_participant", {}).items():
        state["slots_per_participant"][email] = [
            _restore_timeslot(slot) for slot in slots
        ]

    if state.get("ranked_slot") is not None:
        state["ranked_slot"] = _restore_timeslot(state["ranked_slot"])

    return state  # type: ignore[return-value]


def _restore_timeslot(slot: dict) -> dict:
    for key in ("start_utc", "end_utc"):
        val = slot.get(key)
        if isinstance(val, str):
            try:
                dt = datetime.fromisoformat(val)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                slot[key] = dt.astimezone(timezone.utc)
            except ValueError:
                pass
    return slot
