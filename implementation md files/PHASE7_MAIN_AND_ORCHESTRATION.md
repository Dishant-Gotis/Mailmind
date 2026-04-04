# PHASE7_MAIN_AND_ORCHESTRATION.md
## Purpose


---

## Dependencies

- **All previous phases complete**

---

## 1. calendar_auth.py — Complete Implementation

```python
# calendar_auth.py
"""
Google Calendar OAuth 2.0 authentication and service object factory.

Flow:
    1. Check if data/token.json exists and is valid/refreshable.
    2. If not, launch browser-based OAuth flow using credentials.json.
    3. Save the new token to data/token.json.
    4. Return an authenticated googleapiclient.discovery.Resource for Calendar v3.

Files:
    credentials.json    — Downloaded from Google Cloud Console. Path: config.google_credentials_path
    data/token.json     — Auto-generated after first auth. Path: config.google_token_path
                          Listed in .gitignore.

Scopes:
    https://www.googleapis.com/auth/calendar.events
    (create, update, delete events — does NOT grant full calendar read)
"""

from __future__ import annotations

from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from config import config
from logger import get_logger

logger = get_logger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]

# Module-level cache — avoids re-building the service on every tool call
_service = None
_credentials: Credentials | None = None


def get_calendar_service():
    """
    Return an authenticated Google Calendar API v3 service object.
    Refreshes credentials if expired. Runs full OAuth flow on first use.

    Returns:
        googleapiclient.discovery.Resource: Authenticated Calendar v3 service.

    Raises:
        CalendarAPIError: If credentials.json is missing or OAuth flow fails.

    Usage from calendar_manager.py:
        service = get_calendar_service()
        service.events().list(calendarId="primary", ...).execute()
    """
    global _service, _credentials

    if _service is not None and _credentials is not None and _credentials.valid:
        return _service

    creds = _load_or_refresh_credentials()
    _credentials = creds
    _service = build("calendar", "v3", credentials=creds)
    logger.info("Google Calendar service initialised.")
    return _service


def _load_or_refresh_credentials() -> Credentials:
    """
    Load credentials from token.json, refresh if expired, run OAuth flow if absent.

    Returns:
        google.oauth2.credentials.Credentials: Valid credentials object.
    """
    token_path = Path(config.google_token_path)
    creds_path = Path(config.google_credentials_path)

    creds: Credentials | None = None

    # Step 1: Try to load existing token
    if token_path.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        except Exception as exc:
            logger.warning("Failed to load token.json: %s — will re-authenticate.", exc)
            creds = None

    # Step 2: Refresh if expired and refresh_token is present
    if creds and not creds.valid:
        if creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                logger.info("Google Calendar credentials refreshed.")
                _save_token(creds, token_path)
                return creds
            except Exception as exc:
                logger.warning("Token refresh failed: %s — running full OAuth flow.", exc)
                creds = None

    # Step 3: Run full OAuth browser flow
    if not creds:
        if not creds_path.exists():
            from exceptions import CalendarAPIError
            raise CalendarAPIError(
                f"credentials.json not found at '{creds_path}'. "
                "Download it from Google Cloud Console → OAuth 2.0 Clients."
            )
        flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
        creds = flow.run_local_server(port=0)
        _save_token(creds, token_path)
        logger.info("Google Calendar OAuth flow complete. Token saved to %s.", token_path)

    return creds


def _save_token(creds: Credentials, token_path: Path) -> None:
    """Save credentials to token.json for future reuse."""
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json())
    logger.debug("Token saved to %s.", token_path)
```

---

# Maps thread_id → (threading.Event, result_container)
# result_container is a list[str] — mutable container for the approval result
_pending_approvals: dict[str, tuple[threading.Event, list[str]]] = {}

# The running bot application (set on start)
_bot_app = None
_bot_loop: Optional[asyncio.AbstractEventLoop] = None


# ── Public API ─────────────────────────────────────────────────────────────────

def request_approval(draft: str, thread_id: str) -> str:
    """

    Args:
        draft:     The outbound_draft email body to show the operator.
        thread_id: Gmail thread ID — used as callback data prefix.

    Returns:
        str: "approved" | "rejected" | "timeout"

    Called from: approval_node in agent/nodes.py (synchronous context).
    """
    event   = threading.Event()
    result  = ["timeout"]   # default if no operator response
    _pending_approvals[thread_id] = (event, result)

    truncated = draft[:3800] + ("..." if len(draft) > 3800 else "")
    message = (
        f"🤖 *MailMind Approval Request*\n"
        f"Thread: `{thread_id[:40]}`\n\n"
        f"*Draft email:*\n{truncated}\n\n"
        f"Please approve or reject this email."
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Approve",  callback_data=f"approve:{thread_id}"),
            InlineKeyboardButton("❌ Reject",   callback_data=f"reject:{thread_id}"),
        ]
    ])

    # Send message via asyncio future submitted to bot event loop
    future = asyncio.run_coroutine_threadsafe(
        _send_approval_message(message, keyboard),
        _bot_loop,
    )
    try:
        future.result(timeout=5.0)   # Wait up to 5s for message delivery
    except Exception as exc:
        del _pending_approvals[thread_id]
        return "timeout"

    # Wait for operator response
    answer = result[0]
    del _pending_approvals[thread_id]

    if not responded:
        logger.warning(
            "Approval timeout for thread %s — auto-sending.", thread_id,
        )
        return "timeout"

    logger.info("Approval result for thread %s: %s", thread_id, answer)
    return answer


def send_alert(message: str) -> None:
    """
    Send a one-way notification to the operator chat (no buttons).
    Used by error_node and low-confidence flagging.

    Args:
        message: Plain text alert message (no markdown required).
    """
    if _bot_loop is None:
        return
    try:
        asyncio.run_coroutine_threadsafe(
            _send_text_message(f"⚠️ *MailMind Alert*\n\n{message}"),
            _bot_loop,
        ).result(timeout=5.0)
    except Exception as exc:


# ── Bot lifecycle ──────────────────────────────────────────────────────────────

async def start_bot() -> None:
    """
    Runs as a background asyncio task in main.py.
    Registers the callback handler for inline button presses.
    """
    global _bot_app, _bot_loop
    _bot_loop = asyncio.get_event_loop()

    app.add_handler(CallbackQueryHandler(_handle_callback))
    _bot_app = app

    await app.initialize()
    await app.start()
    await app.updater.start_polling(allowed_updates=["callback_query"])


async def stop_bot() -> None:
    global _bot_app
    if _bot_app:
        await _bot_app.updater.stop()
        await _bot_app.stop()
        await _bot_app.shutdown()
```

---

## 3. main.py — Complete Implementation

```python
# main.py
"""
MailMind entrypoint. Run with: python main.py

Startup sequence (in order — every step must succeed before proceeding):
    1. Display startup banner
    2. Load and validate config (pydantic-settings, raises on missing vars)
    3. Initialise database (create tables if not exist)
    4. Seed VIP list from config into participant_preferences
    5. Validate Google Calendar auth (token.json or browser flow)
    7. Start IMAP poller (asyncio task — runs forever)
    8. Block on asyncio event loop

Shutdown (Ctrl+C / SIGINT):
    - IMAP poller is stopped gracefully
    - Process exits with code 0
"""

from __future__ import annotations

import asyncio
import signal
import sys

from agent.loop import run as agent_run
from calendar_auth import get_calendar_service
from config import config
from db import init_db
from exceptions import IMAPConnectionError
from imap_poller import IMAPPoller
from logger import get_logger
from preference_store import seed_vip_list

logger = get_logger(__name__)

BANNER = """
╔══════════════════════════════════════╗
║          M A I L M I N D            ║
║   Autonomous AI Scheduling Agent    ║
║   Team TRIOLOGY | PCCOE Pune        ║
╚══════════════════════════════════════╝
"""


async def main() -> None:
    """
    Async main function — orchestrates all subsystems.
    """
    print(BANNER)

    # ── Step 1: Config validation ─────────────────────────────────────────────
    logger.info("Loading configuration...")
    try:
        # Config is validated on import — this just logs the values
        logger.info("Gmail: %s", config.gmail_address)
        logger.info("Model: %s", config.gemini_model)
        logger.info("Poll interval: %ds", config.imap_poll_interval_seconds)
    except Exception as exc:
        logger.critical("Configuration error: %s", exc)
        sys.exit(1)

    # ── Step 2: Database init ─────────────────────────────────────────────────
    logger.info("Initialising database...")
    try:
        init_db()
    except Exception as exc:
        logger.critical("Database init failed: %s", exc)
        sys.exit(1)

    # ── Step 3: Seed VIP list ─────────────────────────────────────────────────
    if config.vip_email_list:
        vips = [v.strip() for v in config.vip_email_list.split(",") if v.strip()]
        seed_vip_list(vips)
        logger.info("VIP list seeded: %d address(es).", len(vips))

    # ── Step 4: Google Calendar auth ──────────────────────────────────────────
    logger.info("Validating Google Calendar credentials...")
    try:
        get_calendar_service()
        logger.info("Google Calendar: OK")
    except Exception as exc:
        logger.critical("Google Calendar auth failed: %s", exc)
        logger.critical("Run 'python setup.py' to complete the OAuth flow.")
        sys.exit(1)

    bot_task = asyncio.create_task(start_bot())
    await asyncio.sleep(2.0)   # Allow bot to initialise before starting poller

    # ── Step 6: IMAP Poller ───────────────────────────────────────────────────
    logger.info("Starting IMAP poller (polling %s)...", config.gmail_address)
    poller = IMAPPoller(callback=agent_run)

    poller_task = asyncio.create_task(_run_poller(poller))

    # ── Step 7: Register shutdown handler ────────────────────────────────────
    shutdown_event = asyncio.Event()

    def _handle_shutdown(*_):
        logger.info("Shutdown signal received.")
        shutdown_event.set()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _handle_shutdown)
        except NotImplementedError:
            # Windows does not support add_signal_handler for SIGTERM
            signal.signal(sig, _handle_shutdown)

    logger.info("MailMind is running. Press Ctrl+C to stop.")
    await shutdown_event.wait()

    # ── Graceful shutdown ─────────────────────────────────────────────────────
    logger.info("Shutting down...")
    poller.stop()
    poller_task.cancel()
    bot_task.cancel()
    await stop_bot()
    logger.info("MailMind stopped cleanly.")


async def _run_poller(poller: IMAPPoller) -> None:
    """
    Run the IMAP poller. On IMAPConnectionError, log critical and exit.
    This task runs until cancelled by shutdown.
    """
    try:
        await poller.start()
    except IMAPConnectionError as exc:
        logger.critical("IMAP fatal error: %s — shutting down.", exc)
        sys.exit(1)
    except asyncio.CancelledError:
        logger.info("IMAP poller task cancelled.")


if __name__ == "__main__":
    asyncio.run(main())
```

---

## 5. Startup Sequence Table

| Step | What | Success signal | Failure action |
|---|---|---|---|
| 1 | Config load from `.env` | No `ValidationError` | `sys.exit(1)` |
| 2 | SQLite `init_db()` | Tables created | `sys.exit(1)` |
| 3 | VIP list seed via `seed_vip_list()` | Log count | Non-fatal if empty |
| 4 | Calendar `get_calendar_service()` | Returns service object | `sys.exit(1)` — user must run `setup.py` |
| 6 | IMAP `IMAPPoller.start()` | Begins polling INBOX | `IMAPConnectionError` → `sys.exit(1)` |

---

## 6. Asyncio Task Architecture

```
asyncio event loop (single thread)
│     ApplicationBuilder().token(...)
│     app.updater.start_polling()
│
├── Task: poller_task           ← IMAP poller (runs forever)
│     await poller.start()
│     └── await asyncio.to_thread(self._poll_once)  ← each poll cycle in thread pool
│           └── self.callback(thread_id, email_obj)
│                 └── agent_run(thread_id, email_obj)  ← synchronous loop.run()
│
└── await shutdown_event.wait() ← main() blocks here until Ctrl+C
```

**Key concurrency decisions:**
- `asyncio.to_thread()` moves blocking IMAP I/O off the event loop thread
- `agent_run()` is synchronous — it runs in the thread pool worker
- Gemini calls inside agent nodes are synchronous (inside `to_thread`)
- A per-thread_id `asyncio.Lock` is **not** needed because IMAP processing is sequential per poll cycle — one email at a time

---

## 7. Signal Handling — Windows Compatibility

On Windows, `asyncio.loop.add_signal_handler()` raises `NotImplementedError` for `SIGTERM`. `main.py` falls back to `signal.signal()` for Windows compatibility:

```python
for sig in (signal.SIGINT, signal.SIGTERM):
    try:
        loop.add_signal_handler(sig, _handle_shutdown)
    except NotImplementedError:
        signal.signal(sig, _handle_shutdown)   # Windows fallback
```

---

## 9. config.py — Additional Fields for Phase 7

These fields must be added to `Config` in `config.py` if not already present from Phase 1:

```python
# config.py — Phase 7 additions to Config class
from pydantic_settings import BaseSettings

class Config(BaseSettings):
    # ... existing fields ...

    # Google Calendar OAuth
    google_credentials_path: str = "credentials.json"
    google_token_path:        str = "data/token.json"


    # VIP list (comma-separated)
    vip_email_list: str = ""   # "ceo@company.com,cto@company.com"

    # Meeting duration
    meeting_duration_minutes: int = 60
```

---

## 10. Error Handling

| Failure | Where | What Happens |
|---|---|---|
| `credentials.json` missing | `calendar_auth._load_or_refresh_credentials()` | `CalendarAPIError` raised → `main.py` logs critical + `sys.exit(1)` |
| Calendar token expired, refresh fails | `_load_or_refresh_credentials()` | Falls back to full OAuth browser flow |
| Operator does not respond within timeout | `event.wait(timeout=...)` | Returns `False`, `result[0]` stays `"timeout"` |
| `start_bot()` fails (bad token) | `ApplicationBuilder().build()` | Exception propagates to `bot_task`, logged, bot unavailable (approval auto-times out) |
| IMAP fatal error | `imap_poller.start()` | `IMAPConnectionError` raised, caught in `_run_poller()`, `sys.exit(1)` |
| Shutdown signal received | `_handle_shutdown()` | Sets `shutdown_event`, `main()` exits `await`, calls `poller.stop()` + `stop_bot()` |

---

## 11. Integration Checklist

- [ ] `calendar_auth.py` exists — `get_calendar_service()` returns cached service on repeat calls
- [ ] `SCOPES = ["https://www.googleapis.com/auth/calendar.events"]` — EXACT scope string
- [ ] `_load_or_refresh_credentials()` tries token.json → refresh → full flow in that order
- [ ] `_save_token()` creates `data/` directory if missing (`mkdir(parents=True, exist_ok=True)`)
- [ ] `request_approval()` is synchronous — blocks via `threading.Event.wait()`
- [ ] `_handle_callback()` is async — calls `event.set()` to release `request_approval()`
- [ ] `start_bot()` registers `CallbackQueryHandler(_handle_callback)` — no other handlers needed
- [ ] `main.py` has all 6 startup steps in correct order
- [ ] Shutdown handler compatible with Windows (fallback `signal.signal()`)
- [ ] `asyncio.to_thread()` is used in `imap_poller.start()` — not blocking the event loop
- [ ] `config.py` has `google_credentials_path`, `google_token_path`, `meeting_duration_minutes`, `vip_email_list`
- [ ] `data/token.json` is in `.gitignore`
- [ ] Running `python main.py` with all credentials in `.env` starts without error

---

## Cross-Phase References

| Exported | From | Imported By |
|---|---|---|
| `get_calendar_service()` | `calendar_auth.py` | `tools/calendar_manager.py` (P5) `_get_service()` |
| `IMAPPoller` | `imap_poller.py` (P2) | `main.py` (P7) |
| `agent_run` | `agent/loop.py` (P6) | `main.py` (P7) — passed as callback to IMAPPoller |
| `init_db()` | `db.py` (P3) | `main.py` (P7) |
| `seed_vip_list()` | `preference_store.py` (P3) | `main.py` (P7) |

---

*PHASE7_MAIN_AND_ORCHESTRATION.md | Team TRIOLOGY | PCCOE Pune | Problem Statement 03*
