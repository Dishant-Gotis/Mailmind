"""
SQLite connection factory and schema initialiser for MailMind.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from logger import get_logger

logger = get_logger(__name__)

DB_PATH = Path("data") / "mailmind.db"

CREATE_SESSIONS_TABLE = """
CREATE TABLE IF NOT EXISTS sessions (
    thread_id   TEXT PRIMARY KEY,
    state_json  TEXT NOT NULL,
    updated_at  DATETIME NOT NULL
);
"""

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
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(
        str(DB_PATH),
        isolation_level=None,
        check_same_thread=False,
        detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


@contextmanager
def get_db() -> Generator[sqlite3.Connection, None, None]:
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    with get_db() as conn:
        conn.execute(CREATE_SESSIONS_TABLE)
        conn.execute(CREATE_SESSIONS_INDEX)
        conn.execute(CREATE_PARTICIPANT_PREFERENCES_TABLE)
    logger.info("Database initialised at %s", DB_PATH)
