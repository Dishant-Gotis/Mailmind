# PHASE1_CONFIG_AND_ENV.md
## Phase 1 — Configuration, Environment Variables & Credential Setup
**Covers:** All `.env` variables, credential acquisition steps, `setup.py` implementation, startup validation flow
**Files documented:** `.env.example`, `config.py` (already in PHASE1_PROJECT_STRUCTURE.md — referenced here for cross-validation), `setup.py`, `tests/test_config.py` (setup section)

---

## Purpose

This document is the single source of truth for every environment variable, credential, and external API connection that MailMind requires. It gives any developer a complete, step-by-step path from zero accounts to a fully validated running system. It documents exactly what each variable controls, how to obtain it, what a correct value looks like, and what the system does if the value is wrong. The `setup.py` module documented here runs a connection test per API before `main.py` is allowed to run — this is the safety net that catches credential errors before the agent loop processes a single email. Every agent built on later phases assumes this setup phase was completed successfully. If this is skipped or incomplete, all subsequent phases will fail silently or with cryptic errors.

---

## Dependencies

- **Phase 1 — Project Structure** must be complete:
  - `exceptions.py` must exist with `ConfigurationError` defined
  - `config.py` must be implemented as specified in `PHASE1_PROJECT_STRUCTURE.md`
  - `logger.py` must be implemented as specified in `PHASE1_PROJECT_STRUCTURE.md`
  - `requirements.txt` must be installed: `pip install -r requirements.txt`
- **External accounts that must exist before running `setup.py`:**
  - A dedicated Gmail account created for MailMind (must be separate from personal Gmail)
  - Gmail 2-Step Verification enabled on that account
  - Gmail App Password generated for that account
  - A Google Cloud project with Calendar API v3 enabled and OAuth credentials downloaded
  - A Gemini API key from Google AI Studio
- **No previous phase code is imported by `setup.py` directly** — it reimports only `config.py`, `exceptions.py`, and `logger.py`

---

## 1. Complete .env Variable Reference Table

Every variable MailMind reads from the `.env` file. Nothing is read from env that is not in this table.

| Variable Name | Type | Required / Optional | Default | What It Controls | Example Value |
|---|---|---|---|---|---|
| `GMAIL_ADDRESS` | `str` | **Required** | — | The dedicated Gmail address MailMind sends and receives from. Used by both IMAP poller (login) and SMTP sender (From header). | `mailmind-assistant@gmail.com` |
| `GMAIL_APP_PASSWORD` | `str` | **Required** | — | Google App Password (16 chars, dashes allowed). NOT the Gmail account password. Used for both IMAP and SMTP authentication. | `abcd-efgh-ijkl-mnop` |
| `IMAP_POLL_INTERVAL_SECONDS` | `int` | Optional | `30` | How many seconds between each IMAP inbox poll. Minimum allowed: 10. Values below 30 risk Gmail rate-limiting. | `30` |
| `GEMINI_API_KEY` | `str` | **Required** | — | API key for Gemini 2.0 Flash. Used by `gemini_client.py` to authenticate every LLM call. | `AIzaSyABCDEFGHIJKLMNOP1234567` |
| `GEMINI_MODEL` | `str` | Optional | `gemini-2.0-flash` | Gemini model identifier string passed to the OpenAI-compatible endpoint. Do not change unless upgrading intentionally. | `gemini-2.0-flash` |
| `GEMINI_CONFIDENCE_THRESHOLD` | `float` | Optional | `0.7` | Float between 0.0 and 1.0. If Gemini classification confidence is below this value, the email is routed to `error_node` instead of acting. | `0.7` |
| `GOOGLE_CALENDAR_CREDENTIALS_PATH` | `str` | **Required** | `credentials.json` | Path to the OAuth 2.0 `credentials.json` file downloaded from Google Cloud Console. File must exist at startup — `config.py` validates this. | `credentials.json` |
| `GOOGLE_CALENDAR_TOKEN_PATH` | `str` | Optional | `token.json` | Path where the OAuth access + refresh token will be stored after first browser authorization. Auto-created on first run. Do not commit this file. | `token.json` |
| `ATTENDANCE_THRESHOLD` | `float` | Optional | `0.5` | Minimum fraction of participants (0.0 exclusive to 1.0 inclusive) that must be available in a slot for it to be accepted. Below this → request more windows from all participants. | `0.5` |
| `MEETING_DURATION_MINUTES` | `int` | Optional | `60` | Default duration in minutes for created Calendar events. Applied when no explicit duration is stated in the email thread. | `60` |
| `VIP_EMAIL_LIST` | `str` | Optional | `""` (empty) | Comma-separated list of email addresses treated as VIP participants. VIP availability is weighted higher in `rank_slots()`. Leave blank for no VIPs. | `ceo@company.com,cto@company.com` |


---

## 2. Complete .env.example

The exact content of the `.env.example` file in the repository root. Every developer duplicates this to `.env` and fills in real values.

```dotenv
# ─────────────────────────────────────────────────────────────────────────────
# MailMind — Environment Variables
# Copy this file to .env and fill in all REQUIRED values before running.
# Never commit .env — it is in .gitignore.
# ─────────────────────────────────────────────────────────────────────────────

# ── Gmail IMAP + SMTP ─────────────────────────────────────────────────────────

# REQUIRED — The dedicated Gmail address MailMind operates from.
# This must be a separate Gmail account, not a personal one.
# Used as the IMAP login, SMTP From address, and sender identity in all outbound emails.
GMAIL_ADDRESS=mailmind-assistant@gmail.com

# REQUIRED — Gmail App Password (NOT your regular Gmail account password).
# Format: 16 lowercase letters, optionally with dashes every 4 chars.
# Generate at: myaccount.google.com → Security → 2-Step Verification → App passwords
# Select app: "Mail" | Device: "Other (Custom name)" → name it "MailMind"
GMAIL_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx

# OPTIONAL — How often to check the inbox for new emails (in seconds).
# Minimum allowed: 10 seconds. Recommended: 30.
# Values below 30 may trigger Gmail's rate limiter and cause IMAP lockouts.
IMAP_POLL_INTERVAL_SECONDS=30

# ── Gemini LLM ────────────────────────────────────────────────────────────────

# REQUIRED — API key for Gemini 2.0 Flash from Google AI Studio.
# Generate at: aistudio.google.com → Get API key → Create API key in new project
# The key must have access to the Gemini API (not restricted to specific services).
GEMINI_API_KEY=AIzaSy...

# OPTIONAL — Gemini model identifier. Do not change unless intentionally upgrading.
GEMINI_MODEL=gemini-2.0-flash

# OPTIONAL — Confidence threshold for Gemini classification (0.0 to 1.0).
# Emails classified below this confidence are not acted on — they are flagged to operator.
# 0.7 is recommended: high enough to avoid hallucinations, low enough to not over-flag.
GEMINI_CONFIDENCE_THRESHOLD=0.7

# ── Google Calendar OAuth ─────────────────────────────────────────────────────

# REQUIRED — Path to credentials.json downloaded from Google Cloud Console.
# This file identifies your OAuth 2.0 client. It does NOT grant access by itself.
# Download at: console.cloud.google.com → APIs & Services → Credentials → Your OAuth Client → Download JSON
# Rename the downloaded file to credentials.json and place it in the project root.
GOOGLE_CALENDAR_CREDENTIALS_PATH=credentials.json

# OPTIONAL — Where the OAuth access token will be saved after first browser authorization.
# This file is auto-created the first time you run setup.py or main.py.
# It contains your OAuth access + refresh tokens. Do not commit it. It is in .gitignore.
GOOGLE_CALENDAR_TOKEN_PATH=token.json

# ── Agent Behaviour ───────────────────────────────────────────────────────────

# OPTIONAL — Minimum fraction of participants that must be available in a slot.
# 0.5 = at least 50% of all participants must overlap for the slot to be accepted.
# If no slot meets this threshold, the agent emails all participants asking for more windows.
ATTENDANCE_THRESHOLD=0.5

# OPTIONAL — Default duration for created Calendar events, in minutes.
# Applied when no explicit meeting duration is mentioned in the email thread.
MEETING_DURATION_MINUTES=60

# Create a bot at: t.me/BotFather → /newbot → follow prompts → copy the token.
# Format: {bot_id}:{alphanumeric_token}

# Alternatively: send any message to your bot, then call:
# and read the "chat.id" field in the response.

# Set higher for operators who are frequently offline.

# ── VIP Scheduling (Phase 10) ─────────────────────────────────────────────────

# OPTIONAL — Comma-separated list of email addresses that are VIP participants.
# VIP availability is given extra weight in rank_slots() slot scoring.
# These emails are written to participant_preferences table at startup on first run.
# Leave blank (empty string) if no VIPs are configured.
VIP_EMAIL_LIST=ceo@company.com,cto@company.com
```

---

# config.py
from __future__ import annotations

import sys
from pathlib import Path

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from exceptions import ConfigurationError


class Config(BaseSettings):
    """
    Central configuration for MailMind.
    Loaded once at startup from the .env file via pydantic-settings.
    All values are typed and validated. Any invalid or missing REQUIRED value
    raises ConfigurationError with a human-readable message.

    Access from any module:
        from config import config
        print(config.gmail_address)
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,   # GMAIL_ADDRESS and gmail_address both work
        extra="ignore",          # Ignore unknown env vars silently
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
    vip_email_list: str = ""   # comma-separated, empty string = no VIPs

    # ── Derived properties (not in .env — computed from raw fields) ────────────

    @property
    def vip_emails(self) -> list[str]:
        """
        Parse VIP_EMAIL_LIST into a cleaned list of lowercase email strings.
        Returns: [] if VIP_EMAIL_LIST is empty or whitespace-only.
        Example: "CEO@Co.com, cto@co.com" → ["ceo@co.com", "cto@co.com"]
        """
        if not self.vip_email_list.strip():
            return []
        return [e.strip().lower() for e in self.vip_email_list.split(",") if e.strip()]

    @property
    def calendar_credentials_path(self) -> Path:
        """Resolved Path object for credentials.json."""
        return Path(self.google_calendar_credentials_path)

    @property
    def calendar_token_path(self) -> Path:
        """Resolved Path object for token.json."""
        return Path(self.google_calendar_token_path)

    # ── Field validators ───────────────────────────────────────────────────────

    @field_validator("gmail_address")
    @classmethod
    def validate_gmail_address(cls, v: str) -> str:
        """
        Ensures GMAIL_ADDRESS looks like a valid email.
        Raises: ValueError with guidance pointing to the exact .env field.
        """
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError(
                f"GMAIL_ADDRESS '{v}' does not look like a valid email address. "
                "Set a valid Gmail address in your .env file."
            )
        return v.lower().strip()

    @field_validator("gmail_app_password")
    @classmethod
    def validate_app_password(cls, v: str) -> str:
        """
        Validates the App Password length (must be 16 chars after removing dashes/spaces).
        Raises: ValueError with a link to the Google App Password page.
        """
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
                f"GEMINI_CONFIDENCE_THRESHOLD must be between 0.0 and 1.0, got {v}. "
                "Recommended value: 0.7"
            )
        return v

    @field_validator("attendance_threshold")
    @classmethod
    def validate_attendance_threshold(cls, v: float) -> float:
        if not 0.0 < v <= 1.0:
            raise ValueError(
                f"ATTENDANCE_THRESHOLD must be between 0.0 (exclusive) and 1.0 (inclusive), got {v}. "
                "Recommended value: 0.5"
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

    @classmethod
        if v < 0:
            raise ValueError(
                "Set to 0 to always require manual approval."
            )
        return v

    @classmethod
    def validate_chat_id(cls, v: str) -> str:
        """
        """
        stripped = v.strip().lstrip("-")   # allow negative IDs (group chats)
        if not stripped.isdigit():
            raise ValueError(
            )
        return v.strip()

    @model_validator(mode="after")
    def validate_credentials_file_exists(self) -> "Config":
        """
        Validates that credentials.json exists at the specified path.
        This check runs after all field validators.
        Raises: ValueError with download instructions if the file is missing.
        """
        creds_path = Path(self.google_calendar_credentials_path)
        if not creds_path.exists():
            raise ValueError(
                f"GOOGLE_CALENDAR_CREDENTIALS_PATH points to '{creds_path}' which does not exist. "
                "Download credentials.json from:\n"
                "  console.cloud.google.com → APIs & Services → Credentials → "
                "Your OAuth 2.0 Client → Download JSON\n"
                "Rename it to credentials.json and place it in the project root."
            )
        return self


def load_config() -> Config:
    """
    Load and validate configuration from .env file.

    Returns:
        Config: Fully validated configuration singleton.

    Raises:
        ConfigurationError: With a human-readable message if any field
            is missing or fails validation. The process should exit(1) on this error.

    Usage:
        Called once at module level below.
        All other modules import: from config import config
    """
    try:
        return Config()
    except Exception as exc:
        raise ConfigurationError(
            f"MailMind configuration error:\n\n{exc}\n\n"
            "Fix the above issue in your .env file, then restart."
        ) from exc


# Module-level singleton — import this everywhere
# Usage in any module: from config import config
config: Config = load_config()
```

---

## 4. Step-by-Step Credential Acquisition Guide

### 4.1 Gmail App Password Setup

Gmail App Passwords replace your account password for third-party apps like MailMind. They have read/write access scoped to Mail only.

**Exact path through Google Account settings:**

1. Go to **myaccount.google.com** and sign into the dedicated MailMind Gmail account
2. Click **Security** in the left sidebar
3. Under "How you sign in to Google", click **2-Step Verification**
4. If 2-Step Verification is not yet enabled: enable it now (required before App Passwords appear)
5. After enabling, scroll down on the 2-Step Verification page to **App passwords**
6. Click **App passwords** (if it doesn't appear, 2SV is not fully active — complete step 4 again)
7. In the "Select app" dropdown: choose **Mail**
8. In the "Select device" dropdown: choose **Other (Custom name)**
9. Type the name: `MailMind`
10. Click **Generate**
11. A 16-character password appears in a yellow box — copy it immediately, it will not be shown again
12. Format: `xxxx xxxx xxxx xxxx` (shown with spaces, but you may enter it with or without dashes)
13. Paste into `.env` as `GMAIL_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx` (dashes allowed — `config.py` strips them)

**What access does the App Password grant?**
- IMAP read access to the inbox (used by `imap_poller.py`)
- SMTP send access from the account (used by `smtp_sender.py`)
- No access to Google Drive, Calendar, Contacts, or any other Google service

**What to do if App Password does not appear in settings:**
- 2-Step Verification must be active AND a method (phone, authenticator) must be added
- Some Google Workspace accounts (school/company emails) have App Passwords disabled by admin — use a personal Gmail instead

---

### 4.2 Gemini API Key

**Step-by-step:**

1. Go to **aistudio.google.com**
2. Sign in with any Google account (does not need to be the MailMind Gmail)
3. Click **Get API key** in the top navigation
4. Click **Create API key**
   - Choose "Create API key in new project" (creates a dedicated project automatically)
   - Or select an existing Google Cloud project
5. Copy the key — it starts with `AIzaSy` followed by 33 alphanumeric characters
6. Paste into `.env` as `GEMINI_API_KEY=AIzaSy...`

**Rate limits on free tier:**
- Gemini 2.0 Flash: 15 RPM (requests per minute), 1,000,000 TPM (tokens per minute)
- MailMind sends at most 1–3 Gemini calls per email processed — free tier is sufficient for hackathon use

**What to do if you hit quota:**
- The `gemini_client.py` retry logic handles transient 429 errors with exponential backoff
- If quota is genuinely exhausted, `setup.py` will report a Gemini failure at startup

---

### 4.3 Google Calendar OAuth 2.0 Setup

Google Calendar requires OAuth 2.0 — an API key alone is not sufficient because Calendar actions are user-specific.

**Exact steps to get credentials.json:**

1. Go to **console.cloud.google.com**
2. Create a new project (top bar → project selector → "New Project") — name it `MailMind`
3. In the left sidebar: **APIs & Services → Library**
4. Search for **Google Calendar API** → click it → click **Enable**
5. In the left sidebar: **APIs & Services → OAuth consent screen**
   - Choose **External** user type (for personal Gmail) or **Internal** (for Workspace)
   - Fill in: App name: `MailMind`, User support email: your email, Developer email: your email
   - Click **Save and Continue** through all steps
   - On the "Scopes" page: click **Add or Remove Scopes**
   - In the filter box, search for: `calendar`
   - Select: `https://www.googleapis.com/auth/calendar.events` (this is the only scope needed)
   - Click **Update** → **Save and Continue**
   - On "Test users": add the MailMind Gmail address as a test user
   - Click **Save and Continue** → **Back to Dashboard**
6. In the left sidebar: **APIs & Services → Credentials**
7. Click **+ Create Credentials → OAuth client ID**
   - Application type: **Desktop app**
   - Name: `MailMind Desktop`
   - Click **Create**
8. In the popup, click **Download JSON**
9. Rename the downloaded file to `credentials.json`
10. Place it in the MailMind project root directory (same level as `main.py`)
11. Set `.env`: `GOOGLE_CALENDAR_CREDENTIALS_PATH=credentials.json`

**Required OAuth Scope (exact string):**
```
https://www.googleapis.com/auth/calendar.events
```
This scope allows: creating events, reading events (for duplicate check), sending invites. It does NOT allow reading other users' calendars.

**First-time browser authorization (token.json creation):**
- When `setup.py` runs the Calendar connection test for the first time, it opens a browser window
- Sign in with the MailMind Gmail account
- Click **Allow** on the consent screen
- `token.json` is saved automatically at the path in `GOOGLE_CALENDAR_TOKEN_PATH`
- All subsequent runs use the saved token — no browser needed again
- If `token.json` is deleted: re-run `setup.py` and authorize again

---

## 5. Complete setup.py Implementation

`setup.py` validates every external API connection independently. One failure does not block others from being tested. Every check prints a PASS or FAIL with diagnostic detail. Exit code 0 means all checks passed. Exit code 1 means one or more checks failed.

```python
# setup.py
"""
MailMind Setup Validator.
Run this before main.py to verify every external credential and connection.

Usage:
    python setup.py

Exit code 0: All checks passed — proceed to python main.py
Exit code 1: One or more checks failed — fix the reported issues first

Each check runs independently. A failure in one does not prevent the others from running.
"""

from __future__ import annotations

import imaplib
import smtplib
import sys
import time
from pathlib import Path
from typing import Callable

# Load config first — if this fails, nothing else can run
try:
    from config import config
except Exception as exc:
    print(f"\n❌  FATAL: Configuration loading failed\n{exc}\n")
    print("Fix the above errors in your .env file, then re-run setup.py.")
    sys.exit(1)

from logger import get_logger

logger = get_logger("setup")


# ── Result tracking ────────────────────────────────────────────────────────────

RESULTS: dict[str, bool] = {}   # check_name → True (pass) / False (fail)


def record(name: str, passed: bool) -> None:
    """Record a check result and print colored status line."""
    RESULTS[name] = passed
    icon = "✅" if passed else "❌"
    status = "PASS" if passed else "FAIL"
    print(f"  {icon}  {status}  —  {name}")


# ── Individual checks ──────────────────────────────────────────────────────────

def check_config() -> None:
    """
    Verify config loaded successfully (already done above, but report it).
    all have non-empty values.
    """
    print("\n[1/5] Configuration")
    try:
        assert config.gmail_address, "GMAIL_ADDRESS is empty"
        assert config.gmail_app_password, "GMAIL_APP_PASSWORD is empty"
        assert config.gemini_api_key, "GEMINI_API_KEY is empty"
        assert config.calendar_credentials_path.exists(), (
            f"credentials.json not found at: {config.calendar_credentials_path}"
        )
        record("Config loaded and all required fields present", True)
        print(f"     Gmail address:         {config.gmail_address}")
        print(f"     Poll interval:         {config.imap_poll_interval_seconds}s")
        print(f"     Attendance threshold:  {config.attendance_threshold}")
        print(f"     VIP count:             {len(config.vip_emails)}")
    except AssertionError as exc:
        record("Config loaded and all required fields present", False)
        print(f"     Error: {exc}")


def check_imap() -> None:
    """
    Test IMAP connection to imap.gmail.com:993.
    Tests: TCP connection, SSL handshake, IMAP login with App Password.

    Passing result: Server replies OK on login, capability list is returned.
    Failing result: imaplib.error with authentication failure — usually wrong App Password.
    """
    print("\n[2/5] Gmail IMAP Connection (imap.gmail.com:993)")
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        status, capability = mail.capability()
        assert status == "OK", f"CAPABILITY returned: {status}"

        login_status, login_data = mail.login(config.gmail_address, config.gmail_app_password)
        assert login_status == "OK", f"LOGIN returned: {login_status} — {login_data}"

        select_status, select_data = mail.select("INBOX")
        assert select_status == "OK", f"SELECT INBOX returned: {select_status}"
        message_count = int(select_data[0])

        mail.logout()

        record("IMAP login and INBOX select", True)
        print(f"     Connected to: imap.gmail.com:993")
        print(f"     Logged in as: {config.gmail_address}")
        print(f"     INBOX message count: {message_count}")

    except imaplib.IMAP4.error as exc:
        record("IMAP login and INBOX select", False)
        print(f"     IMAP error: {exc}")
        print("     Common causes:")
        print("       - Wrong GMAIL_APP_PASSWORD (verify it is 16 chars)")
        print("       - 2-Step Verification not enabled on the Gmail account")
        print("       - IMAP not enabled: Gmail Settings → See all settings → Forwarding and POP/IMAP → Enable IMAP")
    except Exception as exc:
        record("IMAP login and INBOX select", False)
        print(f"     Unexpected error: {exc}")


def check_smtp() -> None:
    """
    Test SMTP connection to smtp.gmail.com:465.
    Tests: TCP connection, SSL handshake, SMTP login with App Password.
    Does NOT send any email — login is sufficient to verify credentials.

    Passing result: SMTP EHLO response OK, login returns 235 Authentication successful.
    Failing result: smtplib.SMTPAuthenticationError — wrong App Password.
    """
    print("\n[3/5] Gmail SMTP Connection (smtp.gmail.com:465)")
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.ehlo()
            smtp.login(config.gmail_address, config.gmail_app_password)
            record("SMTP login", True)
            print(f"     Connected to: smtp.gmail.com:465")
            print(f"     Logged in as: {config.gmail_address}")
            print("     SMTP send capability: verified (no test email sent)")

    except smtplib.SMTPAuthenticationError as exc:
        record("SMTP login", False)
        print(f"     SMTP authentication error: {exc}")
        print("     Common causes:")
        print("       - GMAIL_APP_PASSWORD is incorrect")
        print("       - App Password was revoked — generate a new one")
        print("       - The Gmail account requires re-verification")
    except Exception as exc:
        record("SMTP login", False)
        print(f"     Unexpected error: {exc}")


def check_gemini() -> None:
    """
    Test Gemini API connectivity by sending a minimal chat completion request.
    Uses the OpenAI-compatible endpoint: https://generativelanguage.googleapis.com/v1beta/openai/
    Sends: a single "ping" message — cheapest possible call.
    Validates: API key works, model name is valid, response is received.

    Passing result: Response object with a non-empty choices list.
    Failing result: openai.AuthenticationError — wrong API key.
    """
    print("\n[4/5] Gemini API Connection")
    try:
        from openai import OpenAI

        client = OpenAI(
            api_key=config.gemini_api_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        )

        response = client.chat.completions.create(
            model=config.gemini_model,
            messages=[{"role": "user", "content": "Reply with the single word: OK"}],
            max_tokens=5,
        )

        reply = response.choices[0].message.content.strip()
        record("Gemini API key valid and model responding", True)
        print(f"     Endpoint: generativelanguage.googleapis.com/v1beta/openai/")
        print(f"     Model: {config.gemini_model}")
        print(f"     Test response: '{reply}'")

    except Exception as exc:
        record("Gemini API key valid and model responding", False)
        print(f"     Error: {exc}")
        print("     Common causes:")
        print("       - GEMINI_API_KEY is invalid or empty")
        print("       - GEMINI_MODEL string is wrong (use: gemini-2.0-flash)")
        print("       - Network blocked: confirm you can reach generativelanguage.googleapis.com")


def check_google_calendar() -> None:
    """
    Test Google Calendar API by listing the user's calendar list.
    On first run: triggers browser OAuth flow → token.json is created.
    On subsequent runs: uses token.json refresh token silently.

    Passing result: Calendar list returns at least 1 calendar (the primary calendar).
    Failing result: google.auth.exceptions.RefreshError — token expired with no refresh possible.

    Exact OAuth scope used: https://www.googleapis.com/auth/calendar.events
    """
    print("\n[5/5] Google Calendar API Connection")
    try:
        import google.auth.transport.requests
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build

        SCOPES = ["https://www.googleapis.com/auth/calendar.events"]
        token_path = config.calendar_token_path
        creds_path = config.calendar_credentials_path

        creds: Credentials | None = None

        if token_path.exists():
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(google.auth.transport.requests.Request())
                print("     Token refreshed automatically from token.json")
            else:
                print("     No valid token found — opening browser for OAuth authorization...")
                print("     Sign in to the MailMind Gmail account and click Allow.")
                flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
                creds = flow.run_local_server(port=0)
                print("     Authorization complete.")

            with open(str(token_path), "w") as token_file:
                token_file.write(creds.to_json())
            print(f"     Token saved to: {token_path}")

        service = build("calendar", "v3", credentials=creds)
        calendar_list = service.calendarList().list().execute()
        primary = next(
            (c for c in calendar_list.get("items", []) if c.get("primary")),
            None,
        )

        record("Google Calendar API connected and calendar list retrieved", True)
        print(f"     Scope granted: {SCOPES[0]}")
        print(f"     Token path: {token_path}")
        if primary:
            print(f"     Primary calendar: {primary.get('summary', 'Unnamed')} ({primary.get('id')})")

    except Exception as exc:
        record("Google Calendar API connected and calendar list retrieved", False)
        print(f"     Error: {exc}")
        print("     Common causes:")
        print("       - credentials.json is wrong or corrupted (re-download from Cloud Console)")
        print("       - OAuth consent screen not configured (see PHASE1_CONFIG_AND_ENV.md Section 4.3)")
        print("       - MailMind Gmail not added as test user on the consent screen")
        print("       - token.json expired and refresh failed — delete token.json and re-run setup.py")


# ── Summary ────────────────────────────────────────────────────────────────────

def print_summary() -> int:
    """
    Print the final pass/fail summary table and return exit code.

    Returns:
        int: 0 if all checks passed, 1 if any check failed.
    """
    passed = sum(1 for v in RESULTS.values() if v)
    total = len(RESULTS)
    failed = total - passed

    print("\n" + "═" * 60)
    print("  MAILMIND SETUP SUMMARY")
    print("═" * 60)

    for check_name, result in RESULTS.items():
        icon = "✅" if result else "❌"
        print(f"  {icon}  {check_name}")

    print("─" * 60)
    print(f"  Passed: {passed}/{total}   Failed: {failed}/{total}")
    print("═" * 60)

    if failed == 0:
        print("\n  ✅  All checks passed. Run: python main.py\n")
        return 0
    else:
        print(f"\n  ❌  {failed} check(s) failed. Fix the issues above before running main.py.\n")
        return 1


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n" + "═" * 60)
    print("  MAILMIND SETUP VALIDATOR")
    print("  Running all connection checks independently...")
    print("═" * 60)

    check_config()
    check_imap()
    check_smtp()
    check_gemini()
    check_google_calendar()

    exit_code = print_summary()
    sys.exit(exit_code)
```

---

## 6. Startup Validation Flow Diagram

What happens, in exact sequence, when `python main.py` is executed before any email is processed:

```
python main.py
     │
     ▼
[1] Python imports config.py at module level
     │
     ├── pydantic-settings reads .env file
     ├── Each field validator runs in field declaration order:
     │       validate_gmail_address()      → checks "@" present
     │       validate_app_password()       → checks 16-char length
     │       validate_confidence_threshold() → checks 0.0–1.0 range
     │       validate_attendance_threshold() → checks 0.0–1.0 range
     │       validate_poll_interval()      → checks >= 10
     │       validate_chat_id()            → checks numeric string
     ├── model_validator runs last:
     │       validate_credentials_file_exists() → checks file at path exists
     │
     ├── If any validator fails:
     │       ConfigurationError raised with human-readable message
     │       main.py catches it, prints message, calls sys.exit(1)
     │       PROCESS HALTS — no IMAP connection is attempted
     │
     └── If all validators pass:
             config singleton created and cached at module level
     │
     ▼
[2] main.py imports logger.py
     │
     └── Logger configured once, ThreadIDFilter installed on root logger
     │
     ▼
[3] main.py imports db.py
     │
     ├── SQLite connection opened to data/mailmind.db (created if not exists)
     ├── sessions table created if not exists
     └── participant_preferences table created if not exists
     │
     ▼
[4] main.py reads config.vip_emails
     │
     ├── For each VIP email in the list:
     │       INSERT OR IGNORE INTO participant_preferences (email, vip) VALUES (?, TRUE)
     └── VIPs are seeded into the database before any email is processed
     │
     ▼
[5] main.py starts asyncio event loop
     │
     └── asyncio.run(start_all())
     │
     ▼
[6] IMAP poller task started
     │
     ├── imaplib.IMAP4_SSL("imap.gmail.com", 993)
     ├── Login with GMAIL_ADDRESS + GMAIL_APP_PASSWORD
     ├── If login fails: IMAPConnectionError logged, retry after 60s
     └── SELECT INBOX → start polling loop
     │
     ▼
     │
     └── First poll runs after IMAP_POLL_INTERVAL_SECONDS seconds
```

If `setup.py` was run successfully before `main.py`, steps 1–4 should complete without any errors. Steps 5–7 may still fail transiently (network issues, token expiry) — those are handled by the retry logic in each module.

---

## 7. Error Handling

### 7.1 Configuration Errors

| Error Scenario | What config.py Does | What the Developer Should Do |
|---|---|---|
| Missing GMAIL_ADDRESS | Pydantic raises ValidationError wrapping ConfigurationError | Add `GMAIL_ADDRESS=...` to `.env` |
| GMAIL_APP_PASSWORD shorter than 16 chars | validate_app_password raises ValueError | Generate a new App Password — old one may be corrupted |
| GEMINI_CONFIDENCE_THRESHOLD=1.5 | validate_confidence_threshold raises ValueError | Set value between 0.0 and 1.0 |
| credentials.json not at specified path | validate_credentials_file_exists raises ValueError | Re-download credentials.json from Google Cloud Console and place in project root |
| .env file missing entirely | pydantic-settings raises an error for every Required field | Create .env from .env.example |

### 7.2 setup.py Connection Errors

| Check | Error | Diagnosis |
|---|---|---|
| IMAP | `IMAP4.error: b'[AUTHENTICATIONFAILED]'` | App Password wrong or 2SV not enabled |
| IMAP | `ConnectionRefusedError` | Network blocking port 993 — try different network |
| SMTP | `SMTPAuthenticationError: (535, ...)` | App Password wrong — generate a new one |
| Gemini | `AuthenticationError: 401` | `GEMINI_API_KEY` is invalid or revoked |
| Gemini | `NotFoundError: 404` | `GEMINI_MODEL` string is wrong |
| Calendar | `FileNotFoundError: credentials.json` | config.py validator should have caught this — check `GOOGLE_CALENDAR_CREDENTIALS_PATH` |
| Calendar | `RefreshError: Token expired` | Delete `token.json` and rerun `setup.py` to re-authorize |

### 7.3 Runtime Startup Errors (main.py)

These errors occur after setup.py passed but before the first email is processed:

| Error | Source | Recovery |
|---|---|---|
| ConfigurationError on import | config.py validation changed after setup.py ran | Fix .env and restart |
| SQLite OperationalError creating tables | Disk full, permission denied on data/ directory | Free disk space or fix permissions |
| IMAP login failure at poller start | Token expired or Gmail account locked | Check Gmail account, re-run setup.py |

---

## 8. Test Cases

### Test Case 1 — Valid .env Loads Without Error

**Scenario:** All required variables are present and valid.
**Input:**
```dotenv
GMAIL_ADDRESS=test@gmail.com
GMAIL_APP_PASSWORD=abcd-efgh-ijkl-mnop
GEMINI_API_KEY=AIzaSyTest12345678901234
GEMINI_CONFIDENCE_THRESHOLD=0.7
ATTENDANCE_THRESHOLD=0.5
GOOGLE_CALENDAR_CREDENTIALS_PATH=credentials.json  # file must exist
```
**Expected output:**
- `Config()` returns without raising
- `config.gmail_address == "test@gmail.com"` (lowercased)
- `config.vip_emails == []` (empty list for missing VIP_EMAIL_LIST)

---

### Test Case 2 — Invalid App Password Raises With Guidance

**Scenario:** Developer copies their Gmail login password instead of App Password.
**Input:**
```dotenv
GMAIL_APP_PASSWORD=mysupersecretpassword123
```
**Expected output:**
- `Config()` raises `ValidationError` wrapping a message containing:
  - The text "App Password" or "16 chars"
  - The URL `myaccount.google.com`
- `load_config()` wraps this in `ConfigurationError`
- No IMAP connection is attempted

---

### Test Case 3 — VIP_EMAIL_LIST Parses to Lowercase List

**Scenario:** Operator sets VIP emails with mixed case and spaces.
**Input:**
```dotenv
VIP_EMAIL_LIST=CEO@Company.com, CTO@Company.com , vp@COMPANY.COM
```
**Expected output:**
- `config.vip_emails == ["ceo@company.com", "cto@company.com", "vp@company.com"]`
- All entries stripped, lowercased, comma-split correctly

---

### Test Case 4 — Negative ATTENDANCE_THRESHOLD Raises

**Scenario:** Developer sets threshold to -0.1 accidentally.
**Input:**
```dotenv
ATTENDANCE_THRESHOLD=-0.1
```
**Expected output:**
- `validate_attendance_threshold` raises `ValueError`
- Message contains: "ATTENDANCE_THRESHOLD must be between 0.0 (exclusive) and 1.0"

---

### Test Case 5 — setup.py Reports All Checks Independently

**Scenario:** IMAP credentials are wrong but all other credentials are correct.
**Expected output of `python setup.py`:**
```
[1/5] Configuration
  ✅  PASS  —  Config loaded and all required fields present
       Gmail address:  test@gmail.com
       ...

[2/5] Gmail IMAP Connection (imap.gmail.com:993)
  ❌  FAIL  —  IMAP login and INBOX select
       IMAP error: [AUTHENTICATIONFAILED] Invalid credentials...
       Common causes:
         - Wrong GMAIL_APP_PASSWORD (verify it is 16 chars)

[3/5] Gmail SMTP Connection (smtp.gmail.com:465)
  ✅  PASS  —  SMTP login
       Connected to: smtp.gmail.com:465
       ...

[4/5] Gemini API Connection
  ✅  PASS  —  Gemini API key valid and model responding
       ...

[5/5] Google Calendar API Connection
  ✅  PASS  —  Google Calendar API connected...

════════════════════════════════════════════
  ❌  1 check(s) failed. Fix the issues above before running main.py.
════════════════════════════════════════════
```
Exit code: 1. The other 4 checks still ran and their results are visible.

---

### Test Case 6 — Approval Timeout of 0 Is Valid (Always Manual)

**Scenario:** Operator wants to always manually review every outbound email.
**Input:**
```dotenv
```
**Expected output:**
- `Config()` loads without error
- This setting will be consumed by `approval_node` in Phase 6 — 0 means "never auto-send, always wait"

---

## 9. Integration Checklist

Before Phase 1 is considered complete and Phase 2 can begin, every item in this checklist must be true:

- [ ] `.env.example` committed to the repository with all 14 variables documented
- [ ] `.env` created from `.env.example` with real values by the developer running setup
- [ ] `config.py` implemented with all fields from Section 3, all validators present
- [ ] `config.py` raises `ConfigurationError` (not a raw pydantic error) for all validation failures
- [ ] `config.py` module-level `config` singleton is importable: `from config import config`
- [ ] `setup.py` implemented as in Section 5 — all 5 checks present
- [ ] `setup.py` exits with code 0 when all checks pass, code 1 when any check fails
- [ ] `setup.py` runs all checks even if earlier ones fail (independence enforced)
- [ ] `python setup.py` passes 5/5 for the developer's own machine with their real credentials
- [ ] Gmail IMAP is confirmed enabled in Gmail settings (not just App Password created)
- [ ] `credentials.json` downloaded from Cloud Console, placed in project root, not committed
- [ ] `token.json` does NOT exist in the repo — first-run browser auth creates it locally
- [ ] OAuth consent screen configured with scope `https://www.googleapis.com/auth/calendar.events`
- [ ] MailMind Gmail address added as a test user on the OAuth consent screen
- [ ] `exceptions.py` exists with `ConfigurationError` — `config.py` imports it
- [ ] `logger.py` exists — `setup.py` uses `get_logger("setup")`
- [ ] `tests/test_config.py` passes: `pytest tests/test_config.py -v` shows all green
- [ ] No `.env`, `credentials.json`, `token.json`, `*.db` files appear in `git status`

---

## Cross-Phase References

Files generated in this phase are imported by every subsequent phase:

| Import | Used By |
|---|---|
| `from config import config` | `imap_poller.py` (P2), `smtp_sender.py` (P2), `gemini_client.py` (P4), `tool_caller.py` (P4), `agent/loop.py` (P6), `main.py` (P7), and every tool module in `tools/` (P5) |
| `from exceptions import ConfigurationError` | `config.py` (P1) |
| `from exceptions import IMAPConnectionError` | `imap_poller.py` (P2) |
| `from exceptions import SMTPConnectionError` | `smtp_sender.py` (P2) |
| `from exceptions import GeminiAPIError` | `gemini_client.py` (P4) |
| `from exceptions import CalendarAPIError` | `tools/calendar_manager.py` (P5) |
| `from exceptions import NodeExecutionError` | `agent/loop.py` (P6) |
| `from logger import get_logger` | Every module created in every phase |

Every module must call `get_logger(__name__)` at the top of the file. Every log call inside the agent loop must pass `extra={"thread_id": state["thread_id"]}` so thread IDs appear in every log line.

---

*PHASE1_CONFIG_AND_ENV.md | Team TRIOLOGY | PCCOE Pune | Problem Statement 03*
