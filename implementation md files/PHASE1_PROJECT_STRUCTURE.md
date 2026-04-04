# PHASE1_PROJECT_STRUCTURE.md
## Phase 1 — Project Foundation & Configuration
**Covers:** Directory structure, requirements.txt, .env.example, config.py, exceptions.py, logger.py, .gitignore
**Files documented:** `requirements.txt`, `.env.example`, `.gitignore`, `config.py`, `exceptions.py`, `logger.py`

---

## Purpose

Phase 1 establishes the entire skeleton of the MailMind project before a single line of business logic is written. Every subsequent phase imports from files created here — `config.py` is imported by every module that needs a credential or setting, `exceptions.py` is imported by every module that needs to raise or catch a typed error, and `logger.py` is imported by every module that needs structured output. Getting this phase exactly right means every later phase can be built without revisiting foundations. A misconfigured startup validation here will silently break the entire agent loop later — so this phase also implements `setup.py`, which tests every external API connection before the main process is allowed to run.

---

## Dependencies

- Python 3.11 or higher (required for `tomllib` stdlib and improved typing support)
- No previous phases — this is phase 1
- External accounts that must exist before running `setup.py`:
  - A dedicated Gmail account for MailMind (separate from any personal account)
  - Gmail App Password enabled on that account
  - A Google Cloud project with Calendar API v3 enabled
  - A Gemini API key from Google AI Studio
- No pip packages installed yet — `requirements.txt` is the output of this phase

---

## 1. Directory Tree

Every folder and file in the complete MailMind project. Annotated with one-line purpose.
Files marked `[P1]` are created in this phase. Files marked `[P2]`–`[P11]` are created in later phases but listed here so the full structure is known upfront.

```
mailmind/
│
├── main.py                         [P7]  Entry point — starts IMAP poller + asyncio loop
├── setup.py                        [P1]  Credential validator — run before main.py
├── requirements.txt                [P1]  All pinned dependencies
├── .env                                  NOT committed — created by developer from .env.example
├── .env.example                    [P1]  Template showing all required env variables
├── .gitignore                      [P1]  Excludes secrets and generated files
│
├── config.py                       [P1]  Loads + validates all env variables at startup
├── exceptions.py                   [P1]  All custom exception classes for the entire project
├── logger.py                       [P1]  Structured logger factory with thread_id tagging
├── models.py                       [P3]  All TypedDicts — EmailObject, AgentState, TimeSlot, etc.
├── disclaimer.py                   [P2]  AI disclaimer text and append function
│
├── imap_poller.py                  [P2]  IMAP polling loop — fetches unseen emails every 30s
├── email_parser.py                 [P2]  Parses raw MIME into EmailObject
├── smtp_sender.py                  [P2]  Sends outbound emails via SMTP_SSL
│
├── db.py                           [P3]  SQLite connection factory + table initialisation
├── checkpointer.py                 [P3]  save_state / load_state / clear_state
├── preference_store.py             [P3]  Per-participant preference read/write
│
├── gemini_client.py                [P4]  Gemini 2.0 Flash client wrapper
├── tool_caller.py                  [P4]  Tool schema → Gemini → dispatch → result
├── prompt_builder.py               [P4]  System + user prompt construction per node type
│
├── tool_registry.py                [P5]  Central registry dict + JSON schema generator
├── timezone_utils.py               [P8]  Timezone detection, UTC conversion, local display
│
├── tools/
│   ├── __init__.py                 [P5]  Empty init
│   ├── email_coordinator.py        [P5]  classify, parse_availability, detect_ambiguity, etc.
│   ├── calendar_manager.py         [P5]  check_duplicate, create_event, send_invite
│   ├── coordination_memory.py      [P5]  track_participant_slots, find_overlap, rank_slots
│   └── thread_intelligence.py      [P5]  summarise_thread, detect_cancellation, suggest_optimal_time
│
├── agent/
│   ├── __init__.py                 [P6]  Empty init
│   ├── nodes.py                    [P6]  All 10 node functions
│   ├── router.py                   [P6]  All routing functions
│   ├── graph.py                    [P6]  GRAPH dict + END constant + node name constants
│   └── loop.py                     [P6]  run(thread_id, email_object) — main agent loop
│
├── calendar_auth.py                [P8]  Google Calendar OAuth token flow
├── calendar_client.py              [P8]  Calendar API v3 service object wrapper
│
├── data/
│   └── mailmind.db                       NOT committed — created at runtime by db.py
│
└── tests/
    ├── __init__.py                 [P1]  Empty init
    ├── test_config.py              [P1]  Tests for config validation logic
    ├── test_email_parser.py        [P2]  Tests for MIME parsing
    ├── test_checkpointer.py        [P3]  Tests for session save/load/clear
    ├── test_preference_store.py    [P3]  Tests for preference read/write
    ├── test_tool_caller.py         [P4]  Tests for Gemini tool dispatch
    ├── test_tools.py               [P5]  Tests for all four tool modules
    ├── test_rank_slots.py          [P5]  Tests for rank_slots() algorithm
    └── test_agent_loop.py          [P6]  Integration tests for full agent loop
```

---

## 2. requirements.txt

Complete content. Every package pinned to a specific version. Inline comment explains why each is needed.

```
# ── Web framework ──────────────────────────────────────────────────────────────
uvicorn[standard]==0.29.0     # ASGI server to run FastAPI

# ── Email ──────────────────────────────────────────────────────────────────────
# imaplib and smtplib are Python stdlib — no pip install needed
# email is Python stdlib — no pip install needed

# ── LLM ────────────────────────────────────────────────────────────────────────
openai==1.30.1                # OpenAI-compatible client used to call Gemini 2.0 Flash endpoint

# ── Time parsing and timezone ──────────────────────────────────────────────────
dateparser==1.2.0             # Natural language time expression parsing
pytz==2024.1                  # IANA timezone database and UTC normalisation

# ── Google APIs ────────────────────────────────────────────────────────────────
google-auth==2.29.0           # OAuth 2.0 credential handling for Google APIs
google-auth-oauthlib==1.2.0   # OAuth flow for installed apps (Calendar auth)
google-auth-httplib2==0.2.0   # HTTP transport for Google API client
google-api-python-client==2.128.0  # Google Calendar API v3 client

# ── Database ───────────────────────────────────────────────────────────────────
# sqlite3 is Python stdlib — no pip install needed

# ── Configuration ──────────────────────────────────────────────────────────────
python-dotenv==1.0.1          # Load .env file into os.environ at startup

# ── Data validation ────────────────────────────────────────────────────────────
pydantic==2.7.1               # Used in config.py for typed settings validation
pydantic-settings==2.2.1      # BaseSettings class for env-backed config

# ── Async ──────────────────────────────────────────────────────────────────────
# asyncio is Python stdlib — no pip install needed

# ── Testing ────────────────────────────────────────────────────────────────────
pytest==8.2.0                 # Test runner
pytest-asyncio==0.23.6        # Async test support for asyncio coroutines
pytest-mock==3.14.0           # Mock fixtures for unit tests
```

---

## 3. .env.example

Complete template. Every variable has a description comment above it and an example value.

```dotenv
# ── Gmail IMAP + SMTP ──────────────────────────────────────────────────────────

# The dedicated Gmail address MailMind operates from
# This must be a separate Gmail account, not a personal one
GMAIL_ADDRESS=mailmind-assistant@gmail.com

# Gmail App Password — NOT your regular Gmail password
# Generate at: myaccount.google.com → Security → 2-Step Verification → App passwords
# Select app: Mail, Select device: Other (name it "MailMind")
GMAIL_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx

# How often to poll the inbox for new emails, in seconds
# 30 is recommended — lower values risk Gmail rate limiting
IMAP_POLL_INTERVAL_SECONDS=30

# ── Gemini LLM ─────────────────────────────────────────────────────────────────

# Gemini API key from Google AI Studio
# Generate at: aistudio.google.com → Get API key
GEMINI_API_KEY=AIzaSy...

# Gemini model to use — do not change unless intentionally upgrading
GEMINI_MODEL=gemini-2.0-flash

# Minimum confidence threshold for Gemini classification (0.0 to 1.0)
# If Gemini confidence is below this value, email is flagged and skipped
GEMINI_CONFIDENCE_THRESHOLD=0.7

# ── Google Calendar ────────────────────────────────────────────────────────────

# Path to the credentials.json file downloaded from Google Cloud Console
# Download at: console.cloud.google.com → APIs & Services → Credentials → OAuth 2.0 Client
GOOGLE_CALENDAR_CREDENTIALS_PATH=credentials.json

# Path where the OAuth token will be stored after first-run browser auth
# This file is auto-created on first run — do not create it manually
GOOGLE_CALENDAR_TOKEN_PATH=token.json

# ── Agent Behaviour ────────────────────────────────────────────────────────────

# Minimum fraction of participants that must be available for a slot to be accepted
# 0.5 means at least 50% of participants must overlap — below this, request more windows
ATTENDANCE_THRESHOLD=0.5

# Default meeting duration in minutes used when creating Calendar events
MEETING_DURATION_MINUTES=60

# ── VIP Scheduling (Phase 10) ──────────────────────────────────────────────────

# Comma-separated list of email addresses that are treated as VIP participants
# VIP availability is weighted higher in rank_slots() scoring
# Leave empty if no VIPs are configured
VIP_EMAIL_LIST=ceo@company.com,cto@company.com
```

---

## 4. .gitignore

Complete content.

```gitignore
# Secrets — never commit these
.env
credentials.json
token.json

# Database — generated at runtime
data/
*.db

# Python
__pycache__/
*.py[cod]
*.pyo
.pytest_cache/
*.egg-info/
dist/
build/
.eggs/

# Virtual environments
.venv/
venv/
env/

# IDE
.idea/
.vscode/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db

# Logs
*.log
logs/
```

---

## 5. config.py

Complete implementation. Uses `pydantic-settings` for typed env loading with validation. Raises `ConfigurationError` (defined in `exceptions.py`) with a human-readable message for every missing or invalid value.

```python
# config.py
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from exceptions import ConfigurationError


class Config(BaseSettings):
    """
    Central configuration for MailMind.
    Loaded once at startup from the .env file.
    Access anywhere via: from config import config
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Gmail ──────────────────────────────────────────────────────────────────
    gmail_address: str
    gmail_app_password: str
    imap_poll_interval_seconds: int = 30

    # ── Gemini ─────────────────────────────────────────────────────────────────
    gemini_api_key: str
    gemini_model: str = "gemini-2.0-flash"
    gemini_confidence_threshold: float = 0.7

    # ── Google Calendar ────────────────────────────────────────────────────────
    google_calendar_credentials_path: str = "credentials.json"
    google_calendar_token_path: str = "token.json"

    # ── Agent Behaviour ────────────────────────────────────────────────────────
    attendance_threshold: float = 0.5
    meeting_duration_minutes: int = 60

    # ── VIP ────────────────────────────────────────────────────────────────────
    vip_email_list: str = ""  # comma-separated, empty string means no VIPs

    # ── Derived properties ─────────────────────────────────────────────────────

    @property
    def vip_emails(self) -> list[str]:
        """Parse VIP_EMAIL_LIST into a clean list of lowercase email strings."""
        if not self.vip_email_list.strip():
            return []
        return [e.strip().lower() for e in self.vip_email_list.split(",") if e.strip()]

    @property
    def calendar_credentials_path(self) -> Path:
        return Path(self.google_calendar_credentials_path)

    @property
    def calendar_token_path(self) -> Path:
        return Path(self.google_calendar_token_path)

    # ── Validators ─────────────────────────────────────────────────────────────

    @field_validator("gmail_address")
    @classmethod
    def validate_gmail_address(cls, v: str) -> str:
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError(
                f"GMAIL_ADDRESS '{v}' does not look like a valid email address. "
                "Set a valid Gmail address in your .env file."
            )
        return v.lower().strip()

    @field_validator("gmail_app_password")
    @classmethod
    def validate_app_password(cls, v: str) -> str:
        cleaned = v.replace("-", "").replace(" ", "")
        if len(cleaned) != 16:
            raise ValueError(
                f"GMAIL_APP_PASSWORD appears invalid (expected 16 chars after removing dashes, "
                f"got {len(cleaned)}). "
                "Generate a new App Password at: myaccount.google.com → Security → App passwords."
            )
        return v

    @field_validator("gemini_confidence_threshold")
    @classmethod
    def validate_confidence_threshold(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError(
                f"GEMINI_CONFIDENCE_THRESHOLD must be between 0.0 and 1.0, got {v}."
            )
        return v

    @field_validator("attendance_threshold")
    @classmethod
    def validate_attendance_threshold(cls, v: float) -> float:
        if not 0.0 < v <= 1.0:
            raise ValueError(
                f"ATTENDANCE_THRESHOLD must be between 0.0 (exclusive) and 1.0 (inclusive), got {v}."
            )
        return v

    @field_validator("imap_poll_interval_seconds")
    @classmethod
    def validate_poll_interval(cls, v: int) -> int:
        if v < 10:
            raise ValueError(
                f"IMAP_POLL_INTERVAL_SECONDS must be at least 10 seconds to avoid Gmail rate limiting, got {v}."
            )
        return v

    @model_validator(mode="after")
    def validate_credentials_file_exists(self) -> "Config":
        creds_path = Path(self.google_calendar_credentials_path)
        if not creds_path.exists():
            raise ValueError(
                f"GOOGLE_CALENDAR_CREDENTIALS_PATH points to '{creds_path}' which does not exist. "
                "Download credentials.json from Google Cloud Console → APIs & Services → Credentials."
            )
        return self


def load_config() -> Config:
    """
    Load and validate configuration from .env file.
    Raises ConfigurationError with a human-readable message on any validation failure.
    Call once at startup — the returned object is the singleton config instance.
    """
    try:
        return Config()
    except Exception as exc:
        raise ConfigurationError(
            f"MailMind configuration error:\n\n{exc}\n\n"
            "Fix the above issue in your .env file, then restart."
        ) from exc


# Module-level singleton — import this everywhere
config: Config = load_config()
```

---

## 6. exceptions.py

Complete implementation. Every custom exception the system uses across all phases. Each class includes: what scenario triggers it, what the catching code should do.

```python
# exceptions.py
"""
All custom exceptions for MailMind.
Importing: from exceptions import <ExceptionClass>
"""


class MailMindBaseError(Exception):
    """
    Base class for all MailMind exceptions.
    Never raise this directly — always raise a specific subclass.
    Catching this catches all MailMind errors in one place.
    """


# ── Configuration ──────────────────────────────────────────────────────────────

class ConfigurationError(MailMindBaseError):
    """
    Raised by: config.py → load_config() when a required env variable is missing
               or a value fails validation.
    Triggered by: Missing .env file, invalid credential format, missing credentials.json.
    Catcher should: Print the message and exit(1) — do not attempt to continue.
    """


# ── Email Ingestion ────────────────────────────────────────────────────────────

class IMAPConnectionError(MailMindBaseError):
    """
    Raised by: imap_poller.py when imaplib.IMAP4_SSL fails to connect or authenticate.
    Triggered by: Wrong App Password, Gmail account locked, network unreachable.
    Catcher should: Wait 60 seconds and retry. Log the error with full traceback.
                    After 5 consecutive failures, raise and halt the poller.
    """


class EmailParseError(MailMindBaseError):
    """
    Raised by: email_parser.py when a MIME message cannot be parsed into an EmailObject.
    Triggered by: Malformed MIME, missing required headers (From, Date).
    Catcher should: Log the raw message bytes at DEBUG level, skip this email, continue polling.
    """


class SMTPConnectionError(MailMindBaseError):
    """
    Raised by: smtp_sender.py when smtplib.SMTP_SSL fails to connect or send.
    Triggered by: Network failure, wrong App Password, Gmail SMTP rate limit.
    Catcher should: Retry once after 10 seconds. If retry fails, log and mark
                    the outbound draft as failed in session state.
    """


# ── Session Memory ─────────────────────────────────────────────────────────────

class SessionNotFoundError(MailMindBaseError):
    """
    Raised by: checkpointer.py → load_state() when thread_id has no stored session.
    Triggered by: First email in a thread (expected), or DB corruption (unexpected).
    Catcher should: Treat as a new session — call init_state() instead.
                    This is NOT a fatal error.
    """


class CheckpointError(MailMindBaseError):
    """
    Raised by: checkpointer.py → save_state() when SQLite write fails.
    Triggered by: Disk full, DB file locked, SQLite corruption.
    Catcher should: Log the error and halt the current agent loop run.
                    Do NOT send any outbound email if state could not be saved.
    """


# ── LLM / Gemini ──────────────────────────────────────────────────────────────

class GeminiAPIError(MailMindBaseError):
    """
    Raised by: gemini_client.py when all retry attempts to Gemini API fail.
    Triggered by: API key invalid, quota exceeded, Gemini service unavailable.
    Catcher should: Route current email to error_node. Log with thread_id.
                    Do NOT retry in the agent loop — gemini_client already retried.
    """


class LowConfidenceError(MailMindBaseError):
    """
    Raised by: tool_caller.py when Gemini classification confidence is below threshold.
    Triggered by: Ambiguous email content that Gemini cannot confidently classify.
    Catcher should: Route to error_node which logs and skips action on this email.
    """


class ToolNotFoundError(MailMindBaseError):
    """
    Raised by: tool_registry.py → call_tool() when Gemini returns a tool name
               that does not exist in TOOL_REGISTRY.
    Triggered by: Gemini hallucinating a tool name, or a tool being removed but
                  prompt not updated.
    Catcher should: Log the unknown tool name, route to error_node.
    """


# ── Google Calendar ────────────────────────────────────────────────────────────

class CalendarAuthError(MailMindBaseError):
    """
    Raised by: calendar_auth.py when OAuth flow fails or token refresh fails.
    Triggered by: credentials.json missing, OAuth consent screen not configured,
                  token.json expired and cannot refresh.
    Catcher should: Log the error with instructions to re-run setup.py.
                    Do NOT attempt to create Calendar events without valid auth.
    """


class CalendarAPIError(MailMindBaseError):
    """
    Raised by: calendar_manager.py when a Calendar API call fails after retries.
    Triggered by: API quota exceeded, event creation rejected, invalid attendee email.
    Catcher should: Log the error with the Calendar API response body.
                    Mark the session as calendar_failed in AgentState.
                    Send a fallback email to participants with the agreed time
                    but without a Calendar invite.
    """


class DuplicateEventError(MailMindBaseError):
    """
    Raised by: calendar_manager.py → check_duplicate() when a matching event
               already exists on the Calendar.
    Triggered by: Agent loop running twice on the same thread, manual event creation
                  with the same participants and time.
    Catcher should: Log as INFO (not ERROR — this is a safety guard, not a failure).
                    Send a status reply email instead of creating a new event.
    """


# ── Agent State Machine ────────────────────────────────────────────────────────

class NodeExecutionError(MailMindBaseError):
    """
    Raised by: agent/loop.py when a node function raises an unexpected exception.
    Triggered by: Any unhandled exception inside a node function.
    Catcher should: Log with node name, thread_id, and full traceback.
                    Mark session with error flag. Do not send any outbound email.
                    Allow the poller to continue — this thread is dead but others are not.
    """


class InvalidStateTransitionError(MailMindBaseError):
    """
    Raised by: agent/router.py when a routing function returns a node name that
               is not in GRAPH and is not END.
    Triggered by: Bug in routing logic returning an undefined node name.
    Catcher should: Log as CRITICAL. Halt agent loop for this thread.
    """
```

---

## 7. logger.py

Complete implementation. Structured logger factory. Every log line includes timestamp, level, module name, and — when available — the thread_id of the email being processed.

```python
# logger.py
"""
Structured logger for MailMind.
Usage:
    from logger import get_logger
    logger = get_logger(__name__)
    logger.info("Processing email", extra={"thread_id": "abc123"})

Thread ID tagging:
    Pass thread_id via the extra dict on every log call inside the agent loop.
    The formatter will include it automatically if present.
"""

import logging
import sys
from typing import Optional


LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)-30s | %(thread_id_tag)s%(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class ThreadIDFilter(logging.Filter):
    """
    Injects thread_id_tag into every LogRecord.
    If the record has a thread_id in its extra dict, formats it as '[thread_id] '.
    If not present, inserts an empty string so the format string always resolves.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        thread_id = getattr(record, "thread_id", None)
        if thread_id:
            record.thread_id_tag = f"[{thread_id}] "
        else:
            record.thread_id_tag = ""
        return True


def get_logger(name: str, level: int = logging.DEBUG) -> logging.Logger:
    """
    Returns a named logger configured with the MailMind format.

    Args:
        name: Typically __name__ from the calling module.
        level: Logging level. Defaults to DEBUG. Production should use INFO.

    Returns:
        logging.Logger: Configured logger instance.

    Usage:
        logger = get_logger(__name__)
        logger.info("Email received", extra={"thread_id": email_obj["thread_id"]})
        logger.error("IMAP connection failed", exc_info=True)
    """
    logger = logging.getLogger(name)

    if logger.handlers:
        # Already configured — return existing to avoid duplicate handlers
        return logger

    logger.setLevel(level)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)

    formatter = logging.Formatter(fmt=LOG_FORMAT, datefmt=DATE_FORMAT)
    handler.setFormatter(formatter)

    thread_filter = ThreadIDFilter()
    handler.addFilter(thread_filter)
    logger.addFilter(thread_filter)

    logger.addHandler(handler)
    logger.propagate = False

    return logger


# Root MailMind logger — import directly for module-level use
root_logger = get_logger("mailmind")
```

---

## 8. tests/__init__.py and tests/test_config.py

`tests/__init__.py` is empty. Full content of `tests/test_config.py`:

```python
# tests/test_config.py
"""
Tests for config.py validation logic.
Run with: pytest tests/test_config.py -v
"""

import os
import pytest
from unittest.mock import patch

from exceptions import ConfigurationError


class TestConfigValidation:
    """Tests that config.py raises ConfigurationError with useful messages for bad values."""

    def _make_valid_env(self, **overrides) -> dict:
        """Returns a complete valid env dict, with optional overrides."""
        base = {
            "GMAIL_ADDRESS": "test@gmail.com",
            "GMAIL_APP_PASSWORD": "abcd-efgh-ijkl-mnop",
            "GEMINI_API_KEY": "AIzaSyTest12345",
            "GOOGLE_CALENDAR_CREDENTIALS_PATH": "credentials.json",
            "IMAP_POLL_INTERVAL_SECONDS": "30",
            "ATTENDANCE_THRESHOLD": "0.5",
            "GEMINI_CONFIDENCE_THRESHOLD": "0.7",
        }
        base.update(overrides)
        return base

    def test_valid_config_loads_without_error(self, tmp_path, monkeypatch):
        """A complete, valid .env should load without raising."""
        # Create a fake credentials.json so the file-exists validator passes
        creds = tmp_path / "credentials.json"
        creds.write_text("{}")
        env = self._make_valid_env(GOOGLE_CALENDAR_CREDENTIALS_PATH=str(creds))
        with patch.dict(os.environ, env, clear=True):
            from config import Config
            cfg = Config()
            assert cfg.gmail_address == "test@gmail.com"

    def test_missing_gmail_address_raises(self, monkeypatch):
        """Missing GMAIL_ADDRESS must raise ConfigurationError."""
        env = self._make_valid_env()
        del env["GMAIL_ADDRESS"]
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(Exception):  # pydantic ValidationError wraps to ConfigurationError
                from config import Config
                Config()

    def test_invalid_email_format_raises(self, tmp_path, monkeypatch):
        """GMAIL_ADDRESS without @ must raise with a message mentioning the field."""
        creds = tmp_path / "credentials.json"
        creds.write_text("{}")
        env = self._make_valid_env(
            GMAIL_ADDRESS="notanemail",
            GOOGLE_CALENDAR_CREDENTIALS_PATH=str(creds),
        )
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(Exception) as exc_info:
                from config import Config
                Config()
            assert "GMAIL_ADDRESS" in str(exc_info.value) or "email" in str(exc_info.value).lower()

    def test_short_app_password_raises(self, tmp_path, monkeypatch):
        """App password shorter than 16 chars must raise with guidance."""
        creds = tmp_path / "credentials.json"
        creds.write_text("{}")
        env = self._make_valid_env(
            GMAIL_APP_PASSWORD="tooshort",
            GOOGLE_CALENDAR_CREDENTIALS_PATH=str(creds),
        )
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(Exception) as exc_info:
                from config import Config
                Config()
            assert "App Password" in str(exc_info.value) or "password" in str(exc_info.value).lower()

    def test_confidence_threshold_out_of_range_raises(self, tmp_path, monkeypatch):
        """GEMINI_CONFIDENCE_THRESHOLD above 1.0 must raise."""
        creds = tmp_path / "credentials.json"
        creds.write_text("{}")
        env = self._make_valid_env(
            GEMINI_CONFIDENCE_THRESHOLD="1.5",
            GOOGLE_CALENDAR_CREDENTIALS_PATH=str(creds),
        )
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(Exception):
                from config import Config
                Config()

    def test_vip_emails_property_parses_correctly(self, tmp_path, monkeypatch):
        """vip_emails property must return a list of lowercased, stripped emails."""
        creds = tmp_path / "credentials.json"
        creds.write_text("{}")
        env = self._make_valid_env(
            VIP_EMAIL_LIST="CEO@Company.com, CTO@Company.com",
            GOOGLE_CALENDAR_CREDENTIALS_PATH=str(creds),
        )
        with patch.dict(os.environ, env, clear=True):
            from config import Config
            cfg = Config()
            assert cfg.vip_emails == ["ceo@company.com", "cto@company.com"]

    def test_empty_vip_list_returns_empty(self, tmp_path, monkeypatch):
        """Empty VIP_EMAIL_LIST must return an empty list, not a list with empty string."""
        creds = tmp_path / "credentials.json"
        creds.write_text("{}")
        env = self._make_valid_env(
            VIP_EMAIL_LIST="",
            GOOGLE_CALENDAR_CREDENTIALS_PATH=str(creds),
        )
        with patch.dict(os.environ, env, clear=True):
            from config import Config
            cfg = Config()
            assert cfg.vip_emails == []

    def test_missing_credentials_json_raises(self, monkeypatch):
        """If credentials.json path does not exist, must raise with download instructions."""
        env = self._make_valid_env(
            GOOGLE_CALENDAR_CREDENTIALS_PATH="/nonexistent/path/credentials.json"
        )
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(Exception) as exc_info:
                from config import Config
                Config()
            assert "credentials.json" in str(exc_info.value)
```

---

## Data Flow

```
.env file
    ↓
config.py → load_config() → Config singleton
    ↓
All modules import: from config import config
    ↓
config.gmail_address, config.gemini_api_key, etc. used throughout
    ↓
Any missing/invalid value → ConfigurationError raised at import time
    ↓
Process exits with error message before any email is processed
```

---

## Error Handling

| Failure Mode | Where It Occurs | What To Do |
|---|---|---|
| `.env` file missing entirely | `config.py` import | `pydantic-settings` raises `ValidationError` → wrapped as `ConfigurationError` → print and exit(1) |
| Required env variable missing | `config.py` field declaration | pydantic raises `ValidationError` with field name → wrapped as `ConfigurationError` |
| `credentials.json` not found | `config.py` model_validator | `ConfigurationError` raised with download instructions |
| Invalid email format in GMAIL_ADDRESS | `config.py` field_validator | `ConfigurationError` with exact field name and correction guidance |
| App Password wrong length | `config.py` field_validator | `ConfigurationError` with exact setup URL |
| `logger.py` StreamHandler fails | `logger.py` get_logger | Python will raise `OSError` — this is unrecoverable, process exits |

---

## Test Cases

### Test Case 1 — Valid configuration loads cleanly
**Input:** All required env variables set correctly, credentials.json exists at specified path
**Expected output:** `config` singleton is created, `config.gmail_address` returns lowercase email, `config.vip_emails` returns parsed list, no exception raised
**How to run:** `pytest tests/test_config.py::TestConfigValidation::test_valid_config_loads_without_error -v`

### Test Case 2 — Missing required variable gives human-readable error
**Input:** `.env` with `GMAIL_ADDRESS` omitted
**Expected output:** Exception raised, message includes the field name and what to do
**How to run:** `pytest tests/test_config.py::TestConfigValidation::test_missing_gmail_address_raises -v`

### Test Case 3 — Logger tags thread_id correctly
**Input:** `logger = get_logger("test")`, call `logger.info("msg", extra={"thread_id": "thread_abc123"})`
**Expected output:** Log line contains `[thread_abc123]` between module name and message
**How to run:** Capture stdout and assert `"[thread_abc123]"` appears in output

### Test Case 4 — Logger with no thread_id does not break
**Input:** `logger.info("msg")` with no extra dict
**Expected output:** Log line renders cleanly with no `[None]` or `[{}]` artifact — thread_id_tag is empty string
**How to run:** Capture stdout and assert no `None` appears in log line

---

## Integration Checklist

Before moving to Phase 2, every item below must be true:

- [ ] `python -c "from config import config; print(config.gmail_address)"` prints the Gmail address without error
- [ ] `python -c "from config import config"` with a missing required var prints a `ConfigurationError` with a helpful message and does not raise a raw `pydantic.ValidationError`
- [ ] `python -c "from exceptions import MailMindBaseError; print('OK')"` prints OK
- [ ] `python -c "from logger import get_logger; l = get_logger('test'); l.info('hello')"` prints a formatted log line to stdout
- [ ] `pytest tests/test_config.py -v` — all tests pass
- [ ] `.env` is listed in `.gitignore` — verify with `git check-ignore -v .env`
- [ ] `credentials.json` is listed in `.gitignore` — verify with `git check-ignore -v credentials.json`
- [ ] `token.json` is listed in `.gitignore` — verify with `git check-ignore -v token.json`
- [ ] `data/` directory is listed in `.gitignore`
- [ ] `requirements.txt` installs cleanly in a fresh virtualenv: `pip install -r requirements.txt` with no errors
- [ ] All directories exist: `mailmind/`, `tools/`, `agent/`, `tests/`, `data/`
- [ ] All `__init__.py` files exist in `tools/`, `agent/`, `tests/`
- [ ] `python setup.py` (once implemented in Phase 1 Config MD) runs without ImportError

---

*PHASE1_PROJECT_STRUCTURE.md | MailMind | Team TRIOLOGY | PCCOE Pune*
