# PHASE10_VIP_SCHEDULING.md
## Phase 10 — VIP Priority Scheduling (Bonus Feature)
**Covers:** `vip` database column, `seed_vip_list()`, `check_vip_status()`, full `rank_slots()` VIP integration, `.env` config, worked numerical example, edge cases
**Files documented:** `preference_store.py` (VIP additions), `config.py` (VIP field), `db.py` (schema), `tests/test_vip_scheduling.py`

---

## Purpose

Phase 10 implements VIP priority scheduling — a bonus feature that ensures scheduling decisions tilt toward times when key stakeholders (CEO, lead client, hiring manager) are available. The VIP weight (`WEIGHT_VIP = 0.15`) was already reserved in `rank_slots()` during Phase 5 and `vip` data was loaded from `check_vip_status()` (mocked as always returning False). Phase 10 makes that real: VIP emails come from `.env`, get seeded into SQLite at startup, and are correctly read at scoring time.

This phase has four distinct steps:
1. Ensure the `vip` column exists in `participant_preferences`
2. Add `vip_email_list` to `Config`
3. Implement `seed_vip_list()` and `check_vip_status()` in `preference_store.py`
4. Confirm `rank_slots()` correctly reads VIP status from the `preferences` dict — no code change needed there if Phase 5 was implemented correctly

---

## Dependencies

- **Phase 1:** `config.py` — add `vip_email_list` field
- **Phase 3:** `db.py` — `participant_preferences` table must have `vip INTEGER DEFAULT 0` column; `preference_store.py` must return `"vip"` key in `load_preferences()` output
- **Phase 5:** `rank_slots()` — already calls `check_vip_status()` and reads `preferences[email]["vip"]`; this phase provides the real implementation
- **Phase 7:** `main.py` — already calls `seed_vip_list()` on startup; this phase implements the function itself

---

## 1. db.py — Schema Verification

The `CREATE TABLE` statement in `init_db()` (written in Phase 3) **must** include the `vip` column. If it was omitted, add a migration.

```python
# db.py — Required final schema for participant_preferences (Phase 3 + Phase 10 additions)

CREATE_PARTICIPANT_PREFERENCES_SQL = """
CREATE TABLE IF NOT EXISTS participant_preferences (
    email                 TEXT PRIMARY KEY,
    preferred_hours_start INTEGER DEFAULT 9,
    preferred_hours_end   INTEGER DEFAULT 17,
    blocked_days          TEXT    DEFAULT '[]',  -- JSON list of weekday name strings
    timezone              TEXT    DEFAULT 'UTC',
    vip                   INTEGER DEFAULT 0,      -- 1 = VIP, 0 = standard
    updated_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_pp_email ON participant_preferences(email);
"""

# Run this in init_db() via conn.executescript(CREATE_PARTICIPANT_PREFERENCES_SQL)
```

**If the table already exists without the `vip` column** (Phase 3 was built before Phase 10 was known), add this migration inside `init_db()` after the main `CREATE TABLE`:

```python
# db.py — add_vip_column migration (safe to run on every startup — no-ops if column exists)

def _add_vip_column_if_missing(conn) -> None:
    """
    Add the vip column to participant_preferences if it was created without it.
    Uses PRAGMA table_info to check before altering — avoids duplicate column error.
    """
    cursor = conn.execute("PRAGMA table_info(participant_preferences)")
    columns = [row[1] for row in cursor.fetchall()]   # row[1] is the column name
    if "vip" not in columns:
        conn.execute("ALTER TABLE participant_preferences ADD COLUMN vip INTEGER DEFAULT 0")
        conn.commit()

# Call _add_vip_column_if_missing(conn) inside init_db() after creating tables.
```

---

## 2. config.py — vip_email_list Field

Add this field to the `Config` class. It was referenced in Phase 7's `main.py` but must actually exist in the class.

```python
# config.py — Phase 10 addition

from pydantic_settings import BaseSettings
from pydantic import field_validator

class Config(BaseSettings):
    # ... all existing fields from Phases 1-7 ...

    # VIP scheduling — comma-separated list of VIP email addresses
    # Example: VIP_EMAIL_LIST=ceo@company.com,cto@company.com
    # Loaded at startup; stored in participant_preferences.vip = 1
    # Empty string means no VIPs configured (vip_score = 1.0 for all slots in rank_slots)
    vip_email_list: str = ""

    @field_validator("vip_email_list", mode="before")
    @classmethod
    def normalise_vip_emails(cls, v: str) -> str:
        """Strip whitespace from each email address in the comma-separated list."""
        if not v:
            return ""
        return ",".join(e.strip().lower() for e in v.split(",") if e.strip())

    @property
    def vip_emails(self) -> list[str]:
        """Return VIP emails as a parsed Python list (convenience property)."""
        if not self.vip_email_list:
            return []
        return self.vip_email_list.split(",")
```

**.env entry example:**
```
VIP_EMAIL_LIST=ceo@company.com,client@partner.com
```

---

## 3. preference_store.py — seed_vip_list() and check_vip_status()

```python
# preference_store.py — Phase 10 additions (append below existing functions)

from db import get_connection
from logger import get_logger

logger = get_logger(__name__)


def seed_vip_list(vip_emails: list[str]) -> None:
    """
    Seed VIP status from config into the database.
    Called ONCE at startup in main.py — the only source of truth for VIP status
    is the .env file; SQLite just caches it.

    Algorithm:
        1. Clear ALL existing VIP flags (so removed VIPs don't persist between restarts)
        2. UPSERT each email with vip=1

    Args:
        vip_emails: Normalised (lowercase, stripped) list of VIP email strings.
                    Pass config.vip_emails here.

    Side effects:
        Writes to participant_preferences table. Creates rows for emails not yet seen.

    Example:
        seed_vip_list(["ceo@company.com", "client@partner.com"])
        # Sets vip=1 for those two; sets vip=0 for all others
    """
    conn = get_connection()
    c = conn.cursor()
    try:
        # Step 1: Reset all VIP flags — ensures removed VIPs lose status on restart
        c.execute("UPDATE participant_preferences SET vip = 0")

        # Step 2: Set VIP flag for each configured email
        for email in vip_emails:
            if not email:
                continue
            c.execute(
                """
                INSERT INTO participant_preferences (email, vip)
                VALUES (?, 1)
                ON CONFLICT(email) DO UPDATE SET vip = 1, updated_at = CURRENT_TIMESTAMP
                """,
                (email,),
            )
        conn.commit()
        logger.info("VIP list seeded: %d address(es) marked as VIP.", len(vip_emails))
    except Exception as exc:
        conn.rollback()
        logger.error("Failed to seed VIP list: %s", exc)
    finally:
        conn.close()


def check_vip_status(email: str) -> bool:
    """
    Check if a participant is a VIP.

    Args:
        email: Email address (case-insensitive — normalised to lowercase internally).

    Returns:
        bool: True if VIP flag is set in participant_preferences, False otherwise.
              Returns False if the email has no row yet (new, never-seen participant).

    Called from: rank_slots() in tools/coordination_memory.py
    Performance: Single indexed SELECT — fast even with thousands of participants.
    """
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "SELECT vip FROM participant_preferences WHERE email = ?",
        (email.strip().lower(),),
    )
    row = c.fetchone()
    conn.close()
    return bool(row[0]) if row else False
```

---

## 4. preference_store.py — Update load_preferences() to Include vip

In Phase 3, `load_preferences()` was implemented. Ensure it includes `vip` in its return dict so `rank_slots()` can use it without extra database calls:

```python
# preference_store.py — update inside load_preferences()

def load_preferences(email: str, load_learning: bool = True) -> dict:
    """
    Load full preference profile for a participant.
    Returns a complete PreferenceProfile-compatible dict.
    """
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        """
        SELECT preferred_hours_start, preferred_hours_end, blocked_days, timezone, vip
        FROM participant_preferences
        WHERE email = ?
        """,
        (email.strip().lower(),),
    )
    row = c.fetchone()
    conn.close()

    if row:
        blocked_days = json.loads(row[2]) if row[2] else []
        vip = bool(row[4])
    else:
        blocked_days = []
        vip = False

    prefs = {
        "email":                  email.lower(),
        "preferred_hours_start":  row[0] if row else 9,
        "preferred_hours_end":    row[1] if row else 17,
        "blocked_days":           blocked_days,
        "timezone":               row[3] if row else "UTC",
        "vip":                    vip,          # ← Phase 10 addition
        "slots":                  [],           # populated by rank_slots_node
        "preferred_hour_buckets": [],           # populated by get_learning_profile (Phase 9)
        "preferred_days":         [],           # populated by get_learning_profile (Phase 9)
    }

    if load_learning:
        from preference_store import get_learning_profile   # Phase 9 function
        utc_hours, top_days = get_learning_profile(email)
        prefs["preferred_hour_buckets"] = utc_hours
        prefs["preferred_days"]         = top_days

    return prefs
```

---

## 5. rank_slots() — VIP Integration Verification (Phase 5)

No code change is needed here IF Phase 5 was implemented correctly. This section exists to verify and cross-reference. The VIP scoring block from Phase 5 should look exactly like this:

```python
# tools/coordination_memory.py — VIP block (Phase 5, verified for Phase 10)

# Identify VIP participants
vip_participants = [
    e for e in all_participants
    if preferences[e].get("vip", False) or check_vip_status(e)
    #    ↑ from load_preferences() dict       ↑ fallback direct DB check
]

# Score VIP availability for this slot
if vip_participants:
    vip_available = 0
    for vip_email in vip_participants:
        vip_slots = preferences[vip_email].get("slots", [])
        if _has_overlap(slot, vip_slots):
            vip_available += 1
    vip_score = vip_available / len(vip_participants)
else:
    # No VIPs configured → full VIP credit (slot is not penalised for missing VIP)
    vip_score = 1.0
```

**Double-source logic:** `preferences[e].get("vip", False) or check_vip_status(e)`

Why both? `preferences[e]` is built from `load_preferences()` which reads the DB once at session start. If `seed_vip_list()` runs _after_ preferences are loaded (race condition), `check_vip_status()` is the live fallback. In practice, startup order in `main.py` guarantees `seed_vip_list()` runs before the IMAP poller starts, so the first branch always hits — but the fallback prevents silent bugs.

---

## 6. Worked Numerical Example — VIP Breaks a Tie

**Setup:**
- 3 participants: Alice (CEO — VIP), Bob, Carol
- 2 candidate slots
- Both slots have identical attendance (all 3 available in both)
- Slot 1: Monday 09:00 UTC — within everyone's preferred hours
- Slot 2: Monday 14:00 UTC — also within all preferred hours

**Without VIP:**
Both slots would score identically on attendance and preference. Chronology picks the earlier one (Slot 1).

**With VIP configured (Alice = CEO):**
In this example, Alice only offered Slot 2 (14:00 UTC) as her availability.

Scoring Slot 1 (09:00):
```
attendance_score = 2/3 = 0.666  (Bob and Carol only — Alice NOT available here)
vip_score        = 0/1 = 0.000  (Alice is VIP and not available)
preference_score = 2/3 = 0.666
chronology_score = 1.0  (earlier)

final = (0.50 * 0.666) + (0.25 * 0.666) + (0.15 * 0.000) + (0.10 * 1.0)
      = 0.333 + 0.167 + 0.000 + 0.100
      = 0.600
```

Scoring Slot 2 (14:00):
```
attendance_score = 3/3 = 1.000  (all available including Alice)
vip_score        = 1/1 = 1.000  (Alice the VIP is available)
preference_score = 1.0
chronology_score = 0.0  (later)

final = (0.50 * 1.0) + (0.25 * 1.0) + (0.15 * 1.0) + (0.10 * 0.0)
      = 0.500 + 0.250 + 0.150 + 0.000
      = 0.900
```

**Winner: Slot 2 (0.900 > 0.600)** — The VIP's availability pulled Slot 2 from being a "later, less preferable" timeslot to the clear winner. The VIP weight didn't just break a tie — it completely reversed the chronology preference.

---

## 7. Edge Cases

| Scenario | Behaviour |
|---|---|
| No VIPs configured (empty `vip_email_list`) | `vip_participants = []` → `vip_score = 1.0` for ALL slots. No penalty for any slot. |
| VIP is not a participant in this thread | VIP is not in `preferences` dict → not in `vip_participants` list → no effect on scoring |
| VIP email added to `.env` after first startup | `seed_vip_list()` runs on next restart → vip=1 set in DB. Next session picks it up. |
| VIP email removed from `.env` | `seed_vip_list()` resets ALL flags to 0 first → removed VIP loses status on restart. |
| Two VIPs, one available, one not | `vip_score = 1/2 = 0.5` → slot gets half the VIP weight. Better than 0 VIP, worse than full VIP. |
| VIP is non-responsive (Phase 11) | VIP is added to `non_responsive`. They are excluded from `all_participants`. `vip_participants` list is also filtered against `non_responsive` before scoring. |

**Non-responsive VIP filter — add this to rank_slots():**
```python
# tools/coordination_memory.py — add after all_participants definition
# (accepts non_responsive as param from rank_slots_node in Phase 11 integration)

# If non_responsive is passed in the preferences dict context:
non_responsive = [e for e in all_participants if preferences[e].get("non_responsive", False)]

# Filter VIP list too:
vip_participants = [
    e for e in all_participants
    if (preferences[e].get("vip", False) or check_vip_status(e))
    and e not in non_responsive
]
```

---

## 8. main.py Startup Call (Phase 7 reference)

This confirms what Phase 7's `main.py` already does:

```python
# main.py — Step 3 (already implemented in Phase 7, confirmed here)

# ── Step 3: Seed VIP list ─────────────────────────────────────────────────────
if config.vip_email_list:
    seed_vip_list(config.vip_emails)   # config.vip_emails is the list property
    logger.info("VIP list seeded: %d address(es).", len(config.vip_emails))
else:
    logger.info("No VIP list configured. All participants scored equally.")
```

---

## 9. Unit Tests — tests/test_vip_scheduling.py

```python
# tests/test_vip_scheduling.py
"""
Tests for VIP scheduling — seeding, checking, and rank_slots() impact.
Run: pytest tests/test_vip_scheduling.py -v
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

import db as db_module
from db import init_db


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(db_module, "DB_PATH", str(db_path))
    init_db()


class TestSeedVipList:
    def test_seeds_vip_flag(self):
        from preference_store import seed_vip_list, check_vip_status
        seed_vip_list(["ceo@company.com"])
        assert check_vip_status("ceo@company.com") is True

    def test_non_vip_returns_false(self):
        from preference_store import seed_vip_list, check_vip_status
        seed_vip_list(["ceo@company.com"])
        assert check_vip_status("intern@company.com") is False

    def test_multiple_vips_all_flagged(self):
        from preference_store import seed_vip_list, check_vip_status
        seed_vip_list(["ceo@company.com", "cto@company.com", "client@partner.com"])
        assert check_vip_status("ceo@company.com") is True
        assert check_vip_status("cto@company.com") is True
        assert check_vip_status("client@partner.com") is True

    def test_reseeding_removes_old_vips(self):
        """Removed VIPs must not persist after restart (new seed call)."""
        from preference_store import seed_vip_list, check_vip_status
        seed_vip_list(["old_ceo@company.com"])
        assert check_vip_status("old_ceo@company.com") is True

        # Re-seed with a different VIP list
        seed_vip_list(["new_ceo@company.com"])
        assert check_vip_status("old_ceo@company.com") is False
        assert check_vip_status("new_ceo@company.com") is True

    def test_empty_seed_is_noop(self):
        from preference_store import seed_vip_list, check_vip_status
        seed_vip_list([])
        assert check_vip_status("anyone@example.com") is False

    def test_case_insensitive_lookup(self):
        from preference_store import seed_vip_list, check_vip_status
        seed_vip_list(["CEO@COMPANY.COM"])
        # check_vip_status normalises to lowercase
        assert check_vip_status("ceo@company.com") is True


class TestCheckVipStatus:
    def test_unknown_email_returns_false(self):
        from preference_store import check_vip_status
        assert check_vip_status("nobody@nowhere.com") is False

    def test_existing_non_vip_returns_false(self):
        from db import get_connection
        conn = get_connection()
        conn.execute(
            "INSERT INTO participant_preferences (email, vip) VALUES (?, 0)",
            ("staff@company.com",),
        )
        conn.commit()
        conn.close()

        from preference_store import check_vip_status
        assert check_vip_status("staff@company.com") is False


class TestRankSlotsWithVIP:
    """Verify that VIP weight correctly influences rank_slots() output."""

    def _slot(self, hour: int, day_offset: int = 0) -> dict:
        base = datetime(2026, 4, 6, hour, 0, tzinfo=timezone.utc)  # Monday
        from datetime import timedelta
        start = base + timedelta(days=day_offset)
        end = start + timedelta(hours=1)
        return {
            "start_utc": start.isoformat(),
            "end_utc":   end.isoformat(),
            "participant": "test",
            "raw_text":  "",
            "timezone":  "UTC",
        }

    def _prefs(self, email: str, vip: bool, slots: list) -> dict:
        return {
            "email": email, "preferred_hours_start": 9, "preferred_hours_end": 17,
            "blocked_days": [], "vip": vip, "timezone": "UTC",
            "slots": slots, "preferred_hour_buckets": [], "preferred_days": [],
        }

    def test_vip_slot_wins_over_non_vip(self):
        slot_9am  = self._slot(9, 0)   # VIP available
        slot_14pm = self._slot(14, 0)  # VIP NOT available (she only offered 9am)

        # Alice (VIP) only has 9am; Bob has both
        prefs = {
            "alice@co.com": self._prefs("alice@co.com", vip=True,  slots=[slot_9am]),
            "bob@co.com":   self._prefs("bob@co.com",   vip=False, slots=[slot_9am, slot_14pm]),
        }

        with patch("tools.coordination_memory.check_vip_status",
                   side_effect=lambda e: e == "alice@co.com"):
            from tools.coordination_memory import rank_slots
            result = rank_slots([slot_9am, slot_14pm], prefs)

        # 9am: both available, VIP available → wins
        assert result["ranked_slot"]["start_utc"] == slot_9am["start_utc"]

    def test_no_vip_configured_both_slots_equal_chronology_wins(self):
        slot_9am  = self._slot(9, 0)
        slot_14pm = self._slot(14, 0)
        prefs = {
            "alice@co.com": self._prefs("alice@co.com", vip=False, slots=[slot_9am, slot_14pm]),
        }
        with patch("tools.coordination_memory.check_vip_status", return_value=False):
            from tools.coordination_memory import rank_slots
            result = rank_slots([slot_9am, slot_14pm], prefs)
        # Without VIP, chronology + preference decide → 9am (within hours, earlier) wins
        assert result["ranked_slot"]["start_utc"] == slot_9am["start_utc"]

    def test_vip_score_zero_when_vip_unavailable(self):
        slot = self._slot(14)  # Only Bob available, not the VIP Alice
        prefs = {
            "alice@co.com": self._prefs("alice@co.com", vip=True,  slots=[]),  # no availability
            "bob@co.com":   self._prefs("bob@co.com",   vip=False, slots=[slot]),
        }
        with patch("tools.coordination_memory.check_vip_status",
                   side_effect=lambda e: e == "alice@co.com"):
            from tools.coordination_memory import rank_slots
            result = rank_slots([slot], prefs)
        # Result still returned (only one candidate) but score < 0.90
        assert result["ranked_slot"] is not None
        assert result["score"] < 0.90   # Missing VIP weight (0.15) reduces score


class TestConfigVipProperty:
    def test_vip_emails_property_parses_list(self, monkeypatch):
        from config import Config
        cfg = Config(
            gmail_address="a@b.com",
            gmail_app_password="pw",
            gemini_api_key="key",
            gemini_model="gemini-2.0-flash",
            imap_host="imap.gmail.com",
            imap_port=993,
            smtp_host="smtp.gmail.com",
            smtp_port=587,
            vip_email_list="ceo@company.com,cto@company.com",
        )
        assert "ceo@company.com" in cfg.vip_emails
        assert "cto@company.com" in cfg.vip_emails
        assert len(cfg.vip_emails) == 2

    def test_empty_vip_list_returns_empty(self):
        from config import Config
        cfg = Config(
            gmail_address="a@b.com",
            gmail_app_password="pw",
            gemini_api_key="key",
            gemini_model="gemini-2.0-flash",
            imap_host="imap.gmail.com",
            imap_port=993,
            smtp_host="smtp.gmail.com",
            smtp_port=587,
            vip_email_list="",
        )
        assert cfg.vip_emails == []
```

---

## 10. Integration Checklist

- [ ] `participant_preferences` table has `vip INTEGER DEFAULT 0` column in `init_db()`
- [ ] `_add_vip_column_if_missing()` migration guard implemented — safe to run on every startup
- [ ] `Config.vip_email_list: str = ""` added to `config.py`
- [ ] `Config.vip_emails` property returns `list[str]` (parses comma-separated string)
- [ ] `Config.normalise_vip_emails` validator strips whitespace and lowercases
- [ ] `.env` template updated with `VIP_EMAIL_LIST=` (blank default)
- [ ] `seed_vip_list()` implemented — resets ALL vip=0 first, then sets vip=1 for each configured email
- [ ] `check_vip_status()` implemented — returns `bool`, normalises email to lowercase, returns False for unknown emails
- [ ] `load_preferences()` returns `"vip": bool` in its output dict
- [ ] `rank_slots()` double-source VIP check: `preferences[e].get("vip", False) or check_vip_status(e)`
- [ ] `rank_slots()` gives `vip_score = 1.0` when `vip_participants == []` (no VIPs configured)
- [ ] Non-responsive VIPs filtered from `vip_participants` list (Phase 11 integration)
- [ ] `main.py startup Step 3` calls `seed_vip_list(config.vip_emails)` — confirmed present from Phase 7
- [ ] `pytest tests/test_vip_scheduling.py -v` passes all tests

---

## Cross-Phase References

| Exported | From | Imported By |
|---|---|---|
| `seed_vip_list()` | `preference_store.py` | `main.py` (P7) startup Step 3 |
| `check_vip_status()` | `preference_store.py` | `rank_slots()` in `tools/coordination_memory.py` (P5) |
| `"vip"` key in `load_preferences()` | `preference_store.py` | `rank_slots_node` in `agent/nodes.py` (P6) when building `enriched_prefs` |
| `Config.vip_emails` | `config.py` | `main.py` (P7) |
| `vip INTEGER` column | `participant_preferences` (db.py P3) | `preference_store.py` (P10) |

---

*PHASE10_VIP_SCHEDULING.md | Team TRIOLOGY | PCCOE Pune | Problem Statement 03*
