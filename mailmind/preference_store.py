"""
Per-participant preference read/write in the participant_preferences table.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from db import get_db
from logger import get_logger

logger = get_logger(__name__)


def store_preferences(
    email: str,
    accepted_slot: Optional[dict] = None,
    preferred_hours_start: Optional[int] = None,
    preferred_hours_end: Optional[int] = None,
    blocked_days: Optional[list[str]] = None,
    vip: Optional[bool] = None,
    timezone_str: Optional[str] = None,
) -> None:
    email = email.lower().strip()

    with get_db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO participant_preferences (email) VALUES (?)",
            (email,),
        )

        if preferred_hours_start is not None:
            conn.execute(
                "UPDATE participant_preferences SET preferred_hours_start = ? WHERE email = ?",
                (preferred_hours_start, email),
            )
        if preferred_hours_end is not None:
            conn.execute(
                "UPDATE participant_preferences SET preferred_hours_end = ? WHERE email = ?",
                (preferred_hours_end, email),
            )
        if blocked_days is not None:
            conn.execute(
                "UPDATE participant_preferences SET blocked_days = ? WHERE email = ?",
                (json.dumps(blocked_days), email),
            )
        if vip is not None:
            conn.execute(
                "UPDATE participant_preferences SET vip = ? WHERE email = ?",
                (1 if vip else 0, email),
            )
        if timezone_str is not None:
            conn.execute(
                "UPDATE participant_preferences SET timezone = ? WHERE email = ?",
                (timezone_str, email),
            )

        if accepted_slot is not None:
            _append_historical_slot(conn, email, accepted_slot)


def load_preferences(email: str) -> dict:
    email = email.lower().strip()
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM participant_preferences WHERE email = ?",
            (email,),
        ).fetchone()

    if row is None:
        return _default_preferences()

    return {
        "preferred_hours_start": row["preferred_hours_start"],
        "preferred_hours_end":   row["preferred_hours_end"],
        "blocked_days":          json.loads(row["blocked_days"] or "[]"),
        "vip":                   bool(row["vip"]),
        "timezone":              row["timezone"] or "UTC",
        "historical_slots":      json.loads(row["historical_slots"] or "[]"),
    }


def get_historical_slots(email: str) -> list[dict]:
    prefs = load_preferences(email)
    return prefs.get("historical_slots", [])


def check_vip_status(email: str) -> bool:
    email = email.lower().strip()
    with get_db() as conn:
        row = conn.execute(
            "SELECT vip FROM participant_preferences WHERE email = ?",
            (email,),
        ).fetchone()
    if row is None:
        return False
    return bool(row["vip"])


def seed_vip_list(vip_emails: list[str]) -> None:
    for email in vip_emails:
        email = email.lower().strip()
        if not email:
            continue
        with get_db() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO participant_preferences (email, vip) VALUES (?, 1)",
                (email,),
            )
            conn.execute(
                "UPDATE participant_preferences SET vip = 1 WHERE email = ?",
                (email,),
            )


def _append_historical_slot(conn, email: str, slot: dict) -> None:
    conn.execute("BEGIN")
    try:
        row = conn.execute(
            "SELECT historical_slots FROM participant_preferences WHERE email = ?",
            (email,),
        ).fetchone()
        existing: list = json.loads(row["historical_slots"] or "[]")

        serialised_slot = {
            k: (v.isoformat() if isinstance(v, datetime) else v)
            for k, v in slot.items()
        }
        existing.append(serialised_slot)

        conn.execute(
            "UPDATE participant_preferences SET historical_slots = ? WHERE email = ?",
            (json.dumps(existing), email),
        )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise


def _default_preferences() -> dict:
    return {
        "preferred_hours_start": 9,
        "preferred_hours_end":   17,
        "blocked_days":          [],
        "vip":                   False,
        "timezone":              "UTC",
        "historical_slots":      [],
    }
