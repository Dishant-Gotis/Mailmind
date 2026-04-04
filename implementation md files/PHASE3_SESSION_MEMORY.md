# PHASE3_SESSION_MEMORY.md
## Phase 3 — SQLite Session Memory & Checkpointer
**Covers:** `db.py`, `checkpointer.py`, `preference_store.py`, `models.py` (AgentState + TimeSlot sections), full SQL schema, serialisation/deserialisation logic, unit tests
**Files documented:** `db.py`, `checkpointer.py`, `preference_store.py`, `models.py` (AgentState + TimeSlot), `tests/test_checkpointer.py`, `tests/test_preference_store.py`

---

## Purpose

Phase 3 gives the agent persistent memory. Without it, the agent would forget every coordination thread the moment a new email arrives — it could never handle multi-day scheduling across many exchanged emails. This phase implements the exact checkpointing concept from LangGraph (save state after every node, load state at re-entry) but using SQLite and plain Python — zero extra infrastructure. Every Gmail thread maps to exactly one session row in SQLite, keyed by `thread_id`. The agent can stop, crash, or restart — on the next email from the same thread, it loads its exact last state and continues from where it stopped. Participant preferences and historical slot data persist across completely different threads, enabling the learning mechanism used in Phase 9.

---

## Dependencies

- **Phase 1 must be complete:** `exceptions.py` (CheckpointError, SessionNotFoundError), `logger.py`, `config.py`
- **Phase 2 must be complete:** `models.py` must already have `EmailObject` defined — Phase 3 adds `AgentState` and `TimeSlot` to the same file
- **Python stdlib:** `sqlite3`, `json`, `datetime` — no pip installs needed for this phase
- **Database file location:** `data/mailmind.db` — created automatically at runtime by `db.py`. The `data/` directory must exist or be created by `db.py`. It is in `.gitignore`.

---

## 1. models.py — AgentState and TimeSlot TypedDicts

Add these to `models.py` below the existing `EmailObject` definition.

```python
# models.py  (Phase 3 additions — append below EmailObject)
from __future__ import annotations

from datetime import datetime
from typing import Optional, TypedDict


class TimeSlot(TypedDict):
    """
    A single availability window for a participant, normalised to UTC.

    Fields:
        start_utc:   UTC-aware datetime — start of the available window.
        end_utc:     UTC-aware datetime — end of the available window.
        participant: Email address of the participant this slot belongs to.
        raw_text:    The original natural language text that was parsed to produce this slot.
                     Stored for debugging and audit. E.g. "Monday 3pm".
        timezone:    IANA timezone string of the participant at time of parsing.
                     E.g. "Asia/Kolkata". Used for display conversion in outbound emails.
    """
    start_utc: datetime
    end_utc: datetime
    participant: str
    raw_text: str
    timezone: str


class AgentState(TypedDict):
    """
    The complete persistent state of one agent session, keyed by thread_id.
    Stored as JSON in the sessions table. Loaded at the start of every agent loop run.
    Saved after every node execution (checkpointed).

    Fields:
        thread_id:              Gmail thread ID — primary key of the session.
        intent:                 Classification output from triage_node.
                                Values: "scheduling" | "update_request" | "reschedule"
                                        | "cancellation" | "noise" | "unknown"
        participants:           Deduplicated list of all participant email addresses
                                encountered in this thread. Includes the original sender.
        slots_per_participant:  Dict mapping participant email → list of TimeSlot dicts.
                                Populated by coordination_node as each reply arrives.
        pending_responses:      List of participant emails who have not yet replied with
                                their availability. Populated in triage_node, depleted
                                as replies arrive.
        ranked_slot:            The best TimeSlot selected by rank_slots_node. None until
                                rank_slots_node has run successfully.
        outbound_draft:         The current outbound email body string. Set by
                                coordination_node, ambiguity_node, rewrite_node. None
                                until first draft is created.
                                Values: "pending" | "approved" | "rejected" | "timeout" | "none"
        preferences:            Dict mapping participant email → their stored preference dict.
                                Loaded from participant_preferences table at session start.
                                Format: { "preferred_hours_start": int, "preferred_hours_end": int,
                                          "blocked_days": list[str], "vip": bool }
        history:                List of dicts representing the full LLM message history for
                                this thread. Each dict: {"role": str, "content": str}.
                                Passed to Gemini on every call for contextual awareness.
        current_node:           Name of the node currently executing or last completed.
                                Used for logging and debugging.
        ambiguity_rounds:       Dict mapping participant email → int count of how many
                                clarification rounds have been attempted with that participant.
                                Used by ambiguity_node to escalate or mark non-responsive.
        non_responsive:         List of participant emails marked as non-responsive after
                                exceeding MAX_CLARIFICATION_ROUNDS. Excluded from overlap
                                computation and rank_slots scoring.
        error:                  Error message string if error_node was triggered. None otherwise.
        created_at:             ISO 8601 UTC string — when the session was first created.
        updated_at:             ISO 8601 UTC string — when the session was last saved.
    """
    thread_id: str
    intent: str
    participants: list[str]
    slots_per_participant: dict[str, list[dict]]   # TimeSlot dicts (JSON-serialised)
    pending_responses: list[str]
    ranked_slot: Optional[dict]                    # TimeSlot dict or None
    outbound_draft: Optional[str]
    approval_status: str
    preferences: dict[str, dict]
    history: list[dict]
    current_node: str
    ambiguity_rounds: dict[str, int]
    non_responsive: list[str]
    error: Optional[str]
    created_at: str
    updated_at: str


def init_state(thread_id: str, email_obj: "EmailObject") -> AgentState:
    """
    Create a blank AgentState for a new thread.
    Called by agent/loop.py when load_state() returns None (first email in a thread).

    Args:
        thread_id:  Gmail thread ID used as the session key.
        email_obj:  The EmailObject that triggered this new session.

    Returns:
        AgentState: Fully initialised state with all fields set to safe defaults.
    """
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
        error=None,
        created_at=now,
        updated_at=now,
    )
```

---

## 2. db.py — Complete Implementation

```python
# db.py
"""
SQLite connection factory and schema initialiser for MailMind.

Responsibilities:
- Returns a sqlite3 connection configured for safe concurrent use
- Creates both tables on first run if they do not exist
- Provides a context manager for safe open/close

Database file: data/mailmind.db
Created automatically on first call to get_connection().
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from logger import get_logger

logger = get_logger(__name__)

DB_PATH = Path("data") / "mailmind.db"

# DDL — run once at startup via init_db()
CREATE_SESSIONS_TABLE = """
CREATE TABLE IF NOT EXISTS sessions (
    thread_id   TEXT PRIMARY KEY,
    state_json  TEXT NOT NULL,
    updated_at  DATETIME NOT NULL
);
"""

# Index on updated_at for efficient cleanup queries (not strictly required but good practice)
CREATE_SESSIONS_INDEX = """
CREATE INDEX IF NOT EXISTS idx_sessions_updated_at ON sessions (updated_at);
"""

CREATE_PARTICIPANT_PREFERENCES_TABLE = """
CREATE TABLE IF NOT EXISTS participant_preferences (
    email                   TEXT PRIMARY KEY,
    preferred_hours_start   INTEGER DEFAULT 9,
    preferred_hours_end     INTEGER DEFAULT 17,
    blocked_days            TEXT    DEFAULT '[]',
    vip                     INTEGER DEFAULT 0,
    historical_slots        TEXT    DEFAULT '[]',
    timezone                TEXT    DEFAULT 'UTC'
);
"""


def get_connection() -> sqlite3.Connection:
    """
    Open and return a SQLite connection to data/mailmind.db.

    Settings applied:
        isolation_level=None  — autocommit mode; callers manage transactions explicitly
        check_same_thread=False — required because async code may hand connection across threads
        detect_types — enables datetime parsing from SQLite DATETIME columns

    Returns:
        sqlite3.Connection: Open connection. Caller is responsible for closing it.

    Note:
        Use get_db() context manager instead of this function directly
        unless you need to manage the connection lifecycle manually.
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(
        str(DB_PATH),
        isolation_level=None,       # autocommit
        check_same_thread=False,
        detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
    )
    conn.row_factory = sqlite3.Row  # allows column access by name: row["thread_id"]
    conn.execute("PRAGMA journal_mode=WAL;")    # Write-Ahead Logging for better concurrency
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


@contextmanager
def get_db() -> Generator[sqlite3.Connection, None, None]:
    """
    Context manager for a SQLite connection. Closes the connection on exit.

    Usage:
        with get_db() as conn:
            conn.execute("SELECT ...", ...)

    Yields:
        sqlite3.Connection: Open, configured connection.
    """
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    """
    Initialise the database — create tables and indexes if they do not exist.
    Safe to call on every startup (all DDL uses IF NOT EXISTS).
    Called once from main.py before the IMAP poller starts.

    Raises:
        sqlite3.OperationalError: If the data/ directory cannot be created or
            the DB file cannot be written (disk full, permission denied).
    """
    with get_db() as conn:
        conn.execute(CREATE_SESSIONS_TABLE)
        conn.execute(CREATE_SESSIONS_INDEX)
        conn.execute(CREATE_PARTICIPANT_PREFERENCES_TABLE)
    logger.info("Database initialised at %s", DB_PATH)
```

---

## 3. checkpointer.py — Complete Implementation

```python
# checkpointer.py
"""
Save, load, and clear AgentState from SQLite sessions table.
This is the LangGraph checkpointer concept implemented in plain Python + SQLite.

Serialisation contract:
    - AgentState → JSON string via _serialise_state()
    - JSON string → AgentState via _deserialise_state()
    - datetime objects are stored as ISO 8601 UTC strings: "2026-04-04T03:45:00+00:00"
    - TimeSlot dicts inside slots_per_participant and ranked_slot follow the same convention
    - None values are stored as JSON null
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

# ISO 8601 format used for all datetime serialisation in this module
DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S+00:00"


# ── Public API ─────────────────────────────────────────────────────────────────

def save_state(thread_id: str, state: AgentState) -> None:
    """
    Serialise and upsert AgentState into the sessions table.
    Called after EVERY node execution in agent/loop.py.

    Args:
        thread_id:  Gmail thread ID — primary key of the session.
        state:      The current AgentState dict to persist.

    Raises:
        CheckpointError: If the SQLite write fails for any reason.
                         The agent loop must NOT send any email if state cannot be saved.
    """
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
        logger.debug(
            "State saved for thread %s (node=%s)", thread_id, state.get("current_node"),
            extra={"thread_id": thread_id},
        )
    except Exception as exc:
        raise CheckpointError(
            f"Failed to save state for thread {thread_id}: {exc}"
        ) from exc


def load_state(thread_id: str) -> Optional[AgentState]:
    """
    Load and deserialise AgentState from the sessions table.
    Called at the start of every agent/loop.py run().

    Args:
        thread_id: Gmail thread ID to look up.

    Returns:
        AgentState: The stored state dict if found.
        None: If no session exists for this thread_id (first email in thread).

    Raises:
        CheckpointError: If the SQLite read or deserialisation fails unexpectedly.
                         A missing row (new thread) returns None, NOT an exception.
    """
    try:
        with get_db() as conn:
            row = conn.execute(
                "SELECT state_json FROM sessions WHERE thread_id = ?",
                (thread_id,),
            ).fetchone()

        if row is None:
            logger.debug("No existing session for thread %s — new thread.", thread_id)
            return None

        state = _deserialise_state(row["state_json"])
        logger.debug(
            "State loaded for thread %s (node=%s)", thread_id, state.get("current_node"),
            extra={"thread_id": thread_id},
        )
        return state

    except Exception as exc:
        raise CheckpointError(
            f"Failed to load state for thread {thread_id}: {exc}"
        ) from exc


def clear_state(thread_id: str) -> None:
    """
    Delete the session record for a thread from the sessions table.
    Called after a meeting is confirmed and the thread coordination is complete.

    Args:
        thread_id: Gmail thread ID whose session should be deleted.

    Note:
        Does NOT raise if the thread_id does not exist — idempotent.
        Does NOT clear participant_preferences — those persist across threads.
    """
    try:
        with get_db() as conn:
            conn.execute(
                "DELETE FROM sessions WHERE thread_id = ?",
                (thread_id,),
            )
        logger.info("Session cleared for thread %s.", thread_id, extra={"thread_id": thread_id})
    except Exception as exc:
        raise CheckpointError(
            f"Failed to clear state for thread {thread_id}: {exc}"
        ) from exc


# ── Serialisation Helpers ──────────────────────────────────────────────────────

def _serialise_state(state: AgentState) -> str:
    """
    Convert AgentState to a JSON string.

    Handles:
        - datetime objects → ISO 8601 UTC string via DATETIME_FORMAT
        - All other types pass through json.dumps directly (str, int, float, list, dict, None)

    Args:
        state: AgentState dict (may contain nested TimeSlot dicts with datetime fields).

    Returns:
        str: JSON string of the entire state.
    """
    def default_serialiser(obj):
        if isinstance(obj, datetime):
            # Ensure UTC before formatting
            if obj.tzinfo is not None:
                obj = obj.astimezone(timezone.utc)
            else:
                obj = obj.replace(tzinfo=timezone.utc)
            return obj.strftime(DATETIME_FORMAT)
        raise TypeError(f"Object of type {type(obj)} is not JSON serialisable")

    return json.dumps(state, default=default_serialiser, ensure_ascii=False)


def _deserialise_state(state_json: str) -> AgentState:
    """
    Convert a JSON string back to an AgentState dict.

    Handles:
        - ISO 8601 datetime strings in slots_per_participant and ranked_slot
          are converted back to UTC-aware datetime objects.
        - All other fields are returned as-is from json.loads.

    Args:
        state_json: JSON string previously produced by _serialise_state().

    Returns:
        AgentState dict with datetime objects restored in TimeSlot fields.
    """
    state: dict = json.loads(state_json)

    # Restore datetime objects in slots_per_participant
    for email, slots in state.get("slots_per_participant", {}).items():
        state["slots_per_participant"][email] = [
            _restore_timeslot(slot) for slot in slots
        ]

    # Restore datetime in ranked_slot if present
    if state.get("ranked_slot") is not None:
        state["ranked_slot"] = _restore_timeslot(state["ranked_slot"])

    return state  # type: ignore[return-value]


def _restore_timeslot(slot: dict) -> dict:
    """
    Convert ISO 8601 string fields in a TimeSlot dict back to UTC-aware datetime objects.

    Args:
        slot: Dict with "start_utc" and "end_utc" as ISO 8601 strings.

    Returns:
        Dict with "start_utc" and "end_utc" as UTC-aware datetime objects.
    """
    for key in ("start_utc", "end_utc"):
        val = slot.get(key)
        if isinstance(val, str):
            try:
                dt = datetime.fromisoformat(val)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                slot[key] = dt.astimezone(timezone.utc)
            except ValueError:
                pass   # leave as string if unparseable — degraded but not fatal
    return slot
```

---

## 4. preference_store.py — Complete Implementation

```python
# preference_store.py
"""
Per-participant preference read/write in the participant_preferences table.

The participant_preferences table stores:
    - Preferred working hours (start/end hour in UTC, 0-23)
    - Blocked days (list of weekday names: ["Friday", "Saturday"])
    - VIP status (boolean)
    - Historical slots (list of accepted slot dicts — used for learning in Phase 9)
    - Detected timezone string (e.g. "Asia/Kolkata")

All JSON fields (blocked_days, historical_slots) are stored as JSON-encoded TEXT.
The read-modify-write of historical_slots is done inside a SQLite BEGIN..COMMIT
transaction to prevent concurrent corruption.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
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
    """
    Upsert participant preference fields. Only provided (non-None) fields are updated.
    If accepted_slot is provided, it is appended to historical_slots atomically.

    Args:
        email:                 Participant email (lowercase). Primary key.
        accepted_slot:         A TimeSlot dict (with datetime objects) representing a
                               confirmed meeting that this participant accepted.
                               Appended to historical_slots JSON list.
        preferred_hours_start: Preferred work start hour in UTC (0–23). E.g. 9 for 9am UTC.
        preferred_hours_end:   Preferred work end hour in UTC (0–23). E.g. 17 for 5pm UTC.
        blocked_days:          List of weekday names.  E.g. ["Friday", "Saturday"].
        vip:                   True if this participant is a VIP.
        timezone_str:          IANA timezone string. E.g. "Asia/Kolkata".

    Note:
        INSERT OR IGNORE is used first to ensure the row exists,
        then individual UPDATE statements apply only the non-None fields.
        historical_slots update is done inside an explicit transaction.
    """
    email = email.lower().strip()

    with get_db() as conn:
        # Ensure row exists with defaults
        conn.execute(
            "INSERT OR IGNORE INTO participant_preferences (email) VALUES (?)",
            (email,),
        )

        # Apply scalar field updates
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

        # Atomic read-modify-write for historical_slots
        if accepted_slot is not None:
            _append_historical_slot(conn, email, accepted_slot)

    logger.debug("Preferences updated for %s.", email)


def load_preferences(email: str) -> dict:
    """
    Load all preference fields for a participant.

    Args:
        email: Participant email address (case-insensitive).

    Returns:
        dict with keys:
            preferred_hours_start (int),
            preferred_hours_end   (int),
            blocked_days          (list[str]),
            vip                   (bool),
            timezone              (str),
            historical_slots      (list[dict])
        Returns defaults if participant has no stored preferences.
    """
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
    """
    Return only the historical_slots list for a participant.
    Used by suggest_optimal_time() in Phase 9.

    Args:
        email: Participant email address.

    Returns:
        list[dict]: List of accepted TimeSlot dicts (start_utc, end_utc as ISO strings).
                    Empty list if participant has no history.
    """
    prefs = load_preferences(email)
    return prefs.get("historical_slots", [])


def check_vip_status(email: str) -> bool:
    """
    Return True if the participant is marked as VIP in the preferences table.

    Args:
        email: Participant email address.

    Returns:
        bool: True if vip=1 in the database. False if not found or vip=0.
    """
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
    """
    Seed VIP status for a list of email addresses at startup.
    Called from main.py using config.vip_emails before the poller starts.
    Uses INSERT OR IGNORE so existing preferences are not overwritten.

    Args:
        vip_emails: List of lowercase email strings from config.vip_emails.
    """
    for email in vip_emails:
        email = email.lower().strip()
        if not email:
            continue
        with get_db() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO participant_preferences (email, vip) VALUES (?, 1)",
                (email,),
            )
            # If row already existed (from a previous run), ensure vip flag is set
            conn.execute(
                "UPDATE participant_preferences SET vip = 1 WHERE email = ?",
                (email,),
            )
    logger.info("Seeded %d VIP email(s) into participant_preferences.", len(vip_emails))


# ── Internal Helpers ───────────────────────────────────────────────────────────

def _append_historical_slot(conn, email: str, slot: dict) -> None:
    """
    Append one accepted TimeSlot to the historical_slots JSON list atomically.
    Runs inside the same connection (and transaction) as the caller.

    Serialisation: datetime objects in slot are converted to ISO 8601 strings
    before appending to the list.

    Args:
        conn:  Active sqlite3.Connection with participant row guaranteed to exist.
        email: Participant email (already lowercased).
        slot:  TimeSlot dict. May contain datetime objects for start_utc / end_utc.
    """
    conn.execute("BEGIN")
    try:
        row = conn.execute(
            "SELECT historical_slots FROM participant_preferences WHERE email = ?",
            (email,),
        ).fetchone()
        existing: list = json.loads(row["historical_slots"] or "[]")

        # Serialise datetime objects in the slot before storing
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
    """Return sensible defaults for a participant with no stored preferences."""
    return {
        "preferred_hours_start": 9,
        "preferred_hours_end":   17,
        "blocked_days":          [],
        "vip":                   False,
        "timezone":              "UTC",
        "historical_slots":      [],
    }
```

---

## 5. Full SQLite Schema Reference

```sql
-- sessions table
-- One row per Gmail thread. thread_id is the session key.
-- state_json contains the full AgentState as a JSON string.
CREATE TABLE IF NOT EXISTS sessions (
    thread_id   TEXT PRIMARY KEY,
    state_json  TEXT NOT NULL,
    updated_at  DATETIME NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sessions_updated_at ON sessions (updated_at);

-- participant_preferences table
-- One row per unique participant email address seen across ALL threads.
-- Persists indefinitely — not cleared when a session ends.
CREATE TABLE IF NOT EXISTS participant_preferences (
    email                   TEXT    PRIMARY KEY,
    preferred_hours_start   INTEGER DEFAULT 9,      -- UTC hour 0-23
    preferred_hours_end     INTEGER DEFAULT 17,     -- UTC hour 0-23
    blocked_days            TEXT    DEFAULT '[]',   -- JSON: ["Friday", "Saturday"]
    vip                     INTEGER DEFAULT 0,      -- SQLite boolean: 0 or 1
    historical_slots        TEXT    DEFAULT '[]',   -- JSON list of accepted slot dicts
    timezone                TEXT    DEFAULT 'UTC'   -- IANA timezone e.g. "Asia/Kolkata"
);
```

**Design decisions:**
- `sessions.state_json` stores the complete `AgentState` as a single JSON blob — no column per field. This avoids a schema migration every time a new field is added to `AgentState`.
- `participant_preferences` uses individual columns (not JSON blob) for the preference fields because they are queried individually (e.g. `SELECT vip FROM ...`).
- `historical_slots` is a JSON TEXT column because it is always read/written as a whole list — never queried by individual slot values.

---

## 6. Datetime Serialisation Contract

| Value | Python type | SQLite storage | Deserialised back to |
|---|---|---|---|
| `start_utc` in TimeSlot | `datetime` (UTC-aware) | `"2026-04-07T09:00:00+00:00"` | `datetime` (UTC-aware) |
| `end_utc` in TimeSlot | `datetime` (UTC-aware) | `"2026-04-07T10:00:00+00:00"` | `datetime` (UTC-aware) |
| `created_at` in AgentState | `str` (ISO 8601) | `"2026-04-04T03:45:00+00:00"` | `str` (left as string) |
| `updated_at` in AgentState | `str` (ISO 8601) | `"2026-04-04T03:45:00+00:00"` | `str` (left as string) |

**Format string:** `"%Y-%m-%dT%H:%M:%S+00:00"` — always UTC, always explicit offset.

**Why `created_at`/`updated_at` stay as strings:** They are used for display and audit only — never compared as datetime objects inside agent logic. Keeping them as strings avoids an extra deserialisation step.

---

## 7. Data Flow

```
New email arrives for thread_id="<root001@example.com>"
    │
    ▼
agent/loop.py: state = load_state(thread_id)
    │
    ├── state is None (first email) → init_state(thread_id, email_obj)
    │       Creates blank AgentState with participants from email_obj
    │
    └── state is AgentState (returning thread) → use as-is
    │
    ▼
agent/loop.py: while state["current_node"] != END:
    │
    ├── node_fn(state) → state  [node modifies state fields]
    │
    ├── save_state(thread_id, state)   ← checkpoint after every node
    │       _serialise_state() → JSON → INSERT OR REPLACE INTO sessions
    │
    └── state["current_node"] = GRAPH[node_name](state)
    │
    ▼
Meeting confirmed → clear_state(thread_id)
    Removes session row. participant_preferences row NOT removed — persists for learning.
    │
    ▼
preference_store.store_preferences(email, accepted_slot=ranked_slot)
    Called for every participant after calendar_node confirms the meeting.
    Appends the accepted TimeSlot to historical_slots for each participant.
```

---

## 8. Error Handling

| Failure | Where | What Happens |
|---|---|---|
| `save_state` SQLite write fails (disk full) | `checkpointer.save_state()` | `CheckpointError` raised, caught in `agent/loop.py`, session flagged, no email sent |
| `load_state` row missing (new thread) | `checkpointer.load_state()` | Returns `None` — not an error, triggers `init_state()` |
| `load_state` JSON deserialisation fails | `_deserialise_state()` | `CheckpointError` raised, caught in loop, routes to `error_node` |
| `store_preferences` transaction fails | `_append_historical_slot()` | `ROLLBACK` executed, exception re-raised, log ERROR, skip preference update |
| Concurrent `save_state` for same `thread_id` | SQLite `ON CONFLICT` clause | Last writer wins — SQLite serialises writes to the same row via WAL locking |
| `data/` directory missing | `db.get_connection()` | `DB_PATH.parent.mkdir(parents=True, exist_ok=True)` creates it automatically |
| `init_db()` during disk full | `db.init_db()` | `sqlite3.OperationalError` propagates to `main.py`, process exits with error message |

---

## 9. Unit Tests

### tests/test_checkpointer.py

```python
# tests/test_checkpointer.py
"""
Tests for checkpointer.py — save, load, update, clear cycle.
Uses a temporary DB file via monkeypatching db.DB_PATH.
Run: pytest tests/test_checkpointer.py -v
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

import db as db_module
from checkpointer import clear_state, load_state, save_state
from db import init_db
from models import AgentState, TimeSlot, init_state, EmailObject


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    """Redirect DB_PATH to a temp directory for each test."""
    monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "test.db")
    init_db()


def _make_email_obj() -> EmailObject:
    return EmailObject(
        message_id="<msg001@example.com>",
        thread_id="<root001@example.com>",
        sender_email="alice@example.com",
        sender_name="Alice",
        subject="Team sync",
        body="Let's meet.",
        timestamp=datetime(2026, 4, 4, 9, 0, tzinfo=timezone.utc),
        in_reply_to="",
        recipients=["mailmind@gmail.com"],
    )


def _make_state(thread_id: str = "<root001@example.com>") -> AgentState:
    return init_state(thread_id, _make_email_obj())


class TestSaveAndLoad:
    """Test case 1 — save then load returns identical state."""

    def test_save_then_load_returns_same_state(self):
        state = _make_state()
        state["intent"] = "scheduling"
        save_state(state["thread_id"], state)

        loaded = load_state(state["thread_id"])
        assert loaded is not None
        assert loaded["thread_id"] == state["thread_id"]
        assert loaded["intent"] == "scheduling"

    def test_load_nonexistent_thread_returns_none(self):
        result = load_state("<nonexistent@example.com>")
        assert result is None

    def test_save_updates_updated_at(self):
        state = _make_state()
        original_updated = state["updated_at"]
        import time; time.sleep(0.01)
        save_state(state["thread_id"], state)
        loaded = load_state(state["thread_id"])
        # updated_at is written by save_state, not the original state
        assert loaded["updated_at"] >= original_updated


class TestUpdateOverwrites:
    """Test case 2 — saving twice with different values overwrites correctly."""

    def test_update_overwrites_existing_session(self):
        state = _make_state()
        state["intent"] = "noise"
        save_state(state["thread_id"], state)

        state["intent"] = "scheduling"
        state["current_node"] = "coordination_node"
        save_state(state["thread_id"], state)

        loaded = load_state(state["thread_id"])
        assert loaded["intent"] == "scheduling"
        assert loaded["current_node"] == "coordination_node"


class TestClear:
    """Test case 3 — clear removes the session, load returns None after clear."""

    def test_clear_removes_session(self):
        state = _make_state()
        save_state(state["thread_id"], state)
        clear_state(state["thread_id"])
        assert load_state(state["thread_id"]) is None

    def test_clear_nonexistent_thread_does_not_raise(self):
        clear_state("<does_not_exist@example.com>")   # should not raise


class TestDatetimeSerialisation:
    """Test case 4 — datetime objects in TimeSlot survive serialisation roundtrip."""

    def test_timeslot_datetimes_survive_roundtrip(self):
        state = _make_state()
        slot = {
            "start_utc": datetime(2026, 4, 7, 9, 0, tzinfo=timezone.utc),
            "end_utc":   datetime(2026, 4, 7, 10, 0, tzinfo=timezone.utc),
            "participant": "alice@example.com",
            "raw_text": "Monday 9am",
            "timezone": "UTC",
        }
        state["slots_per_participant"]["alice@example.com"] = [slot]
        save_state(state["thread_id"], state)

        loaded = load_state(state["thread_id"])
        recovered_slot = loaded["slots_per_participant"]["alice@example.com"][0]

        assert isinstance(recovered_slot["start_utc"], datetime)
        assert recovered_slot["start_utc"].tzinfo == timezone.utc
        assert recovered_slot["start_utc"].hour == 9

    def test_ranked_slot_datetimes_restored(self):
        state = _make_state()
        state["ranked_slot"] = {
            "start_utc": datetime(2026, 4, 8, 14, 0, tzinfo=timezone.utc),
            "end_utc":   datetime(2026, 4, 8, 15, 0, tzinfo=timezone.utc),
            "participant": "alice@example.com",
            "raw_text": "Tuesday 2pm",
            "timezone": "Asia/Kolkata",
        }
        save_state(state["thread_id"], state)
        loaded = load_state(state["thread_id"])
        assert isinstance(loaded["ranked_slot"]["start_utc"], datetime)
```

### tests/test_preference_store.py

```python
# tests/test_preference_store.py
"""
Tests for preference_store.py.
Run: pytest tests/test_preference_store.py -v
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

import db as db_module
from db import init_db
from preference_store import (
    check_vip_status,
    get_historical_slots,
    load_preferences,
    seed_vip_list,
    store_preferences,
)


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "test.db")
    init_db()


class TestLoadPreferences:
    """Test case 5 — load returns defaults for unknown participant."""

    def test_unknown_participant_returns_defaults(self):
        prefs = load_preferences("unknown@example.com")
        assert prefs["preferred_hours_start"] == 9
        assert prefs["preferred_hours_end"] == 17
        assert prefs["blocked_days"] == []
        assert prefs["vip"] is False
        assert prefs["timezone"] == "UTC"
        assert prefs["historical_slots"] == []


class TestStoreAndLoad:
    """Test case 6 — stored preferences are loaded back correctly."""

    def test_store_and_load_blocked_days(self):
        store_preferences("bob@example.com", blocked_days=["Friday", "Saturday"])
        prefs = load_preferences("bob@example.com")
        assert prefs["blocked_days"] == ["Friday", "Saturday"]

    def test_store_vip_flag(self):
        store_preferences("ceo@company.com", vip=True)
        assert check_vip_status("ceo@company.com") is True

    def test_store_timezone(self):
        store_preferences("alice@example.com", timezone_str="Asia/Kolkata")
        prefs = load_preferences("alice@example.com")
        assert prefs["timezone"] == "Asia/Kolkata"


class TestHistoricalSlots:
    """Test case 7 — historical_slots appends correctly and atomically."""

    def test_append_one_slot(self):
        slot = {
            "start_utc": datetime(2026, 4, 7, 9, 0, tzinfo=timezone.utc),
            "end_utc":   datetime(2026, 4, 7, 10, 0, tzinfo=timezone.utc),
            "participant": "alice@example.com",
            "raw_text": "Monday 9am",
            "timezone": "UTC",
        }
        store_preferences("alice@example.com", accepted_slot=slot)
        slots = get_historical_slots("alice@example.com")
        assert len(slots) == 1
        assert slots[0]["participant"] == "alice@example.com"

    def test_append_multiple_slots_accumulates(self):
        slot1 = {
            "start_utc": datetime(2026, 4, 7, 9, 0, tzinfo=timezone.utc),
            "end_utc":   datetime(2026, 4, 7, 10, 0, tzinfo=timezone.utc),
            "participant": "alice@example.com",
            "raw_text": "Monday 9am", "timezone": "UTC",
        }
        slot2 = {
            "start_utc": datetime(2026, 4, 14, 9, 0, tzinfo=timezone.utc),
            "end_utc":   datetime(2026, 4, 14, 10, 0, tzinfo=timezone.utc),
            "participant": "alice@example.com",
            "raw_text": "Monday 9am next week", "timezone": "UTC",
        }
        store_preferences("alice@example.com", accepted_slot=slot1)
        store_preferences("alice@example.com", accepted_slot=slot2)
        slots = get_historical_slots("alice@example.com")
        assert len(slots) == 2


class TestSeedVipList:
    """Test case 8 — seed_vip_list writes VIP flags without overwriting other preferences."""

    def test_seed_sets_vip_flag(self):
        seed_vip_list(["cto@company.com"])
        assert check_vip_status("cto@company.com") is True

    def test_seed_does_not_overwrite_existing_blocked_days(self):
        store_preferences("cto@company.com", blocked_days=["Saturday"])
        seed_vip_list(["cto@company.com"])
        prefs = load_preferences("cto@company.com")
        assert prefs["blocked_days"] == ["Saturday"]
        assert prefs["vip"] is True

    def test_unknown_email_in_seed_returns_vip_true(self):
        seed_vip_list(["new_vip@company.com"])
        assert check_vip_status("new_vip@company.com") is True
```

---

## 10. Integration Checklist

- [ ] `models.py` has `TimeSlot` TypedDict with all 5 fields
- [ ] `models.py` has `AgentState` TypedDict with all 15 fields
- [ ] `models.py` has `init_state(thread_id, email_obj) -> AgentState` function
- [ ] `db.py` implements `get_connection()`, `get_db()` context manager, `init_db()`
- [ ] `db.init_db()` creates both tables with `IF NOT EXISTS` — safe on every startup
- [ ] WAL mode is set: `conn.execute("PRAGMA journal_mode=WAL;")`
- [ ] `conn.row_factory = sqlite3.Row` is set so row fields are accessible by name
- [ ] `checkpointer.save_state()` uses `ON CONFLICT DO UPDATE` (upsert — not INSERT then UPDATE)
- [ ] `checkpointer.load_state()` returns `None` for missing thread, not `SessionNotFoundError`
- [ ] `checkpointer.clear_state()` is idempotent — no error if thread_id does not exist
- [ ] `_serialise_state()` handles `datetime` objects via custom `default_serialiser`
- [ ] `_deserialise_state()` restores `datetime` objects in `slots_per_participant` and `ranked_slot`
- [ ] `preference_store.store_preferences()` uses `INSERT OR IGNORE` then `UPDATE` pattern
- [ ] `_append_historical_slot()` uses explicit `BEGIN` / `COMMIT` / `ROLLBACK` transaction
- [ ] `preference_store.seed_vip_list()` is idempotent — safe to call on every startup
- [ ] `data/mailmind.db` is listed in `.gitignore` — not committed
- [ ] `pytest tests/test_checkpointer.py -v` passes all tests
- [ ] `pytest tests/test_preference_store.py -v` passes all tests
- [ ] Running `save_state` twice on same thread_id produces one row, not two

---

## Cross-Phase References

| Exported | From | Imported By |
|---|---|---|
| `AgentState` TypedDict | `models.py` | `agent/nodes.py` (P6), `agent/loop.py` (P6), `agent/router.py` (P6), all tool modules (P5) |
| `TimeSlot` TypedDict | `models.py` | `tools/coordination_memory.py` (P5), `tools/email_coordinator.py` (P5), all rank_slots logic (P5) |
| `init_state()` | `models.py` | `agent/loop.py` (P6) — called when `load_state()` returns None |
| `save_state()` | `checkpointer.py` | `agent/loop.py` (P6) — called after every node |
| `load_state()` | `checkpointer.py` | `agent/loop.py` (P6) — called at session start |
| `clear_state()` | `checkpointer.py` | `agent/nodes.py` (P6) — called after `calendar_node` confirms meeting |
| `store_preferences()` | `preference_store.py` | `tools/coordination_memory.py` (P5), `agent/nodes.py` (P6, post-calendar) |
| `load_preferences()` | `preference_store.py` | `tools/coordination_memory.py` (P5), `agent/loop.py` (P6, to populate state.preferences) |
| `get_historical_slots()` | `preference_store.py` | `tools/thread_intelligence.py` (P5) — `suggest_optimal_time()` |
| `check_vip_status()` | `preference_store.py` | `tools/coordination_memory.py` (P5) — `rank_slots()` |
| `seed_vip_list()` | `preference_store.py` | `main.py` (P7) — called once at startup with `config.vip_emails` |
| `init_db()` | `db.py` | `main.py` (P7) — called once before poller starts |
| `get_db()` | `db.py` | `checkpointer.py`, `preference_store.py` — every DB access |

---

*PHASE3_SESSION_MEMORY.md | Team TRIOLOGY | PCCOE Pune | Problem Statement 03*
