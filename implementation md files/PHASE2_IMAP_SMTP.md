# PHASE2_IMAP_SMTP.md
## Phase 2 — Email Ingestion Layer (IMAP + SMTP)
**Covers:** `imap_poller.py`, `email_parser.py`, `smtp_sender.py`, `disclaimer.py`, `EmailObject` TypedDict, thread header handling, unit tests
**Files documented:** `imap_poller.py`, `email_parser.py`, `smtp_sender.py`, `disclaimer.py`, `models.py` (EmailObject section), `tests/test_email_parser.py`

---

## Purpose

Phase 2 is the nervous system of MailMind. It handles all raw email movement — pulling unread emails from Gmail into the agent and pushing agent-authored replies back out. Every component uses Python stdlib only (`imaplib`, `smtplib`, `email`) — no third-party email library. The IMAP poller runs continuously and hands off a typed `EmailObject` to the agent state machine for every new email. The SMTP sender fires outbound emails with correct threading headers so Gmail groups them in the same thread. The disclaimer module is the single mandatory append that cannot be bypassed at any call site. Getting this layer right is the prerequisite for every other phase — no agent logic runs without email in, and no agent decision becomes visible without email out.

---

## Dependencies

- **Phase 1 must be complete:**
  - `from config import config` — provides `gmail_address`, `gmail_app_password`, `imap_poll_interval_seconds`
  - `from exceptions import IMAPConnectionError, SMTPConnectionError, EmailParseError` — all used here
  - `from logger import get_logger` — used in every file
  - `setup.py` must have passed IMAP and SMTP checks
- **Python stdlib only for this phase** — no pip installs beyond what Phase 1 already defined
- **`models.py` is partially created here** — `EmailObject` TypedDict is defined. Later phases add `AgentState`, `TimeSlot`, `PreferenceProfile` to the same file.

---

## 1. EmailObject TypedDict — models.py (Phase 2 section)

```python
# models.py  (Phase 2 adds EmailObject — later phases add more TypedDicts to this same file)
from __future__ import annotations

from datetime import datetime
from typing import TypedDict


class EmailObject(TypedDict):
    """
    Normalised representation of a single inbound email.
    Produced by email_parser.py. Consumed by agent/loop.py run().

    Fields:
        message_id:   The unique Gmail Message-ID header value (e.g. '<abc123@mail.gmail.com>').
                      Used as the In-Reply-To and References header when replying.
        thread_id:    Derived from the References header chain (first Message-ID in the chain).
                      Used as the session key in SQLite — all emails in a Gmail thread share this.
        sender_email: Lowercase email address of the sender (extracted from the From header).
        sender_name:  Display name of the sender. Empty string if not present.
        subject:      Raw Subject header value. Stripping of "Re: " is NOT done here.
        body:         Plain-text body. Extracted from text/plain part. HTML stripped.
                      Leading/trailing whitespace removed. Never None — empty string if no body.
        timestamp:    UTC-aware datetime parsed from the Date header. Timezone-normalised.
        in_reply_to:  Value of the In-Reply-To header. Empty string if not present (first email).
        recipients:   Combined list of all To and CC addresses (lowercase). Includes sender.
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
```

---

## 2. disclaimer.py — Complete Implementation

```python
# disclaimer.py
"""
Single source of truth for the mandatory AI disclaimer.
Every outbound email must include this text — it is appended at send level in smtp_sender.py.
No caller can bypass it because smtp_sender.py calls append_disclaimer() unconditionally.
"""

DISCLAIMER_TEXT = (
    "\n\n---\n"
    "This email was composed and sent by MailMind, an AI scheduling assistant. "
    "It acts autonomously on behalf of the meeting organiser. "
    "If you have concerns or wish to speak to a human, please reply and a human will follow up."
)


def append_disclaimer(body: str) -> str:
    """
    Append the mandatory AI disclaimer to an email body.

    Args:
        body: The email body text before disclaimer. May be empty string.

    Returns:
        str: body with DISCLAIMER_TEXT appended. The disclaimer is always the last content.

    Note:
        This function is called exclusively by smtp_sender.send_reply().
        Callers must never append the disclaimer themselves — always pass the raw body here.
    """
    return body.rstrip() + DISCLAIMER_TEXT
```

---

## 3. email_parser.py — Complete Implementation

```python
# email_parser.py
"""
Parses a raw MIME email byte string into a typed EmailObject.

Key behaviors:
- Extracts plain text from multipart/alternative (prefers text/plain over text/html)
- Derives thread_id from References header chain (first Message-ID = thread root)
- Falls back to Message-ID as thread_id when References is absent (first email in thread)
- Parses Date header to UTC-aware datetime via email.utils.parsedate_to_datetime
- Normalises all email addresses to lowercase
- Never returns None for any field — uses empty string or empty list as sentinel
"""

from __future__ import annotations

import email
import email.utils
from datetime import datetime, timezone
from email.message import Message
from typing import Optional

from exceptions import EmailParseError
from logger import get_logger
from models import EmailObject

logger = get_logger(__name__)


def parse_email(raw_bytes: bytes) -> EmailObject:
    """
    Parse raw MIME bytes into an EmailObject.

    Args:
        raw_bytes: Raw MIME email content as returned by imaplib fetch.
                   Example: b'From: Alice <alice@example.com>\\r\\nDate: ...'

    Returns:
        EmailObject: Fully populated typed dict.

    Raises:
        EmailParseError: If From header or Date header is missing (email is unparseable).

    Usage:
        email_obj = parse_email(raw_mime_bytes)
        agent_loop.run(email_obj["thread_id"], email_obj)
    """
    try:
        msg: Message = email.message_from_bytes(raw_bytes)
    except Exception as exc:
        raise EmailParseError(f"email.message_from_bytes failed: {exc}") from exc

    # ── Required headers ───────────────────────────────────────────────────────
    from_header = msg.get("From", "")
    if not from_header:
        raise EmailParseError("Email has no From header — cannot process.")

    date_header = msg.get("Date", "")
    if not date_header:
        raise EmailParseError("Email has no Date header — cannot determine timestamp.")

    # ── Parse sender ───────────────────────────────────────────────────────────
    sender_name, sender_email = email.utils.parseaddr(from_header)
    sender_email = sender_email.lower().strip()
    sender_name = sender_name.strip()

    # ── Parse Message-ID ───────────────────────────────────────────────────────
    message_id = msg.get("Message-ID", "").strip()

    # ── Derive thread_id from References header ────────────────────────────────
    # References header contains space-separated list of all ancestor Message-IDs.
    # The FIRST Message-ID in this list is the root of the thread — use as session key.
    # If References is absent (first email in a new thread), use Message-ID itself.
    references_header = msg.get("References", "").strip()
    if references_header:
        # Split on whitespace — each token is a Message-ID like <abc@gmail.com>
        all_refs = references_header.split()
        thread_id = all_refs[0].strip()     # first = root of thread
    else:
        # No References → this IS the first email in the thread
        thread_id = message_id if message_id else _generate_fallback_id(sender_email, date_header)

    # ── Parse In-Reply-To ─────────────────────────────────────────────────────
    in_reply_to = msg.get("In-Reply-To", "").strip()

    # ── Parse Subject ─────────────────────────────────────────────────────────
    subject = msg.get("Subject", "").strip()

    # ── Parse recipients (To + CC) ────────────────────────────────────────────
    recipients: list[str] = []
    for header_name in ("To", "Cc"):
        header_val = msg.get(header_name, "")
        if header_val:
            for _, addr in email.utils.getaddresses([header_val]):
                clean = addr.lower().strip()
                if clean and clean not in recipients:
                    recipients.append(clean)

    # ── Parse timestamp ───────────────────────────────────────────────────────
    timestamp = _parse_date_header(date_header)

    # ── Extract plain text body ───────────────────────────────────────────────
    body = _extract_plain_text(msg)

    email_obj: EmailObject = {
        "message_id": message_id,
        "thread_id": thread_id,
        "sender_email": sender_email,
        "sender_name": sender_name,
        "subject": subject,
        "body": body,
        "timestamp": timestamp,
        "in_reply_to": in_reply_to,
        "recipients": recipients,
    }

    logger.debug(
        f"Parsed email: subject='{subject}' sender={sender_email} thread={thread_id}",
        extra={"thread_id": thread_id},
    )
    return email_obj


def _extract_plain_text(msg: Message) -> str:
    """
    Extract the plain-text body from a MIME message.

    Strategy:
    1. If message is not multipart: return decoded payload if content-type is text/plain.
    2. If multipart/alternative: iterate parts, prefer text/plain, skip text/html.
    3. If multipart/mixed: recurse into each part, collect all text/plain parts, join with newline.
    4. If no text/plain found anywhere: return empty string (never raise — body is optional).

    Args:
        msg: A parsed email.message.Message object.

    Returns:
        str: Plain text body, stripped of leading/trailing whitespace. Never None.
    """
    collected: list[str] = []

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            disposition = part.get("Content-Disposition", "")

            # Skip attachments
            if "attachment" in disposition:
                continue

            if content_type == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    try:
                        collected.append(payload.decode(charset, errors="replace"))
                    except Exception:
                        collected.append(payload.decode("utf-8", errors="replace"))

            # Skip text/html parts entirely — we never parse HTML
    else:
        if msg.get_content_type() == "text/plain":
            payload = msg.get_payload(decode=True)
            if payload:
                charset = msg.get_content_charset() or "utf-8"
                collected.append(payload.decode(charset, errors="replace"))

    return "\n".join(collected).strip()


def _parse_date_header(date_str: str) -> datetime:
    """
    Parse the Date header string into a UTC-aware datetime.

    Args:
        date_str: Raw Date header value, e.g. 'Mon, 04 Apr 2026 09:15:00 +0530'.

    Returns:
        datetime: UTC-aware datetime. If parsing fails, returns datetime.now(UTC).

    Note:
        email.utils.parsedate_to_datetime handles most RFC 2822 date formats.
        Result is converted to UTC explicitly to ensure all timestamps in the system are UTC.
    """
    try:
        dt = email.utils.parsedate_to_datetime(date_str)
        # Convert to UTC if timezone-aware
        if dt.tzinfo is not None:
            return dt.astimezone(timezone.utc)
        else:
            # Naive datetime — assume UTC
            return dt.replace(tzinfo=timezone.utc)
    except Exception:
        logger.warning(f"Failed to parse Date header: '{date_str}' — using current UTC time.")
        return datetime.now(timezone.utc)


def _generate_fallback_id(sender_email: str, date_str: str) -> str:
    """
    Generate a deterministic fallback thread_id when Message-ID is missing.
    This should almost never trigger — legitimate Gmail emails always have Message-ID.

    Args:
        sender_email: Sender's email address.
        date_str: Raw Date header string.

    Returns:
        str: A synthetic thread ID string. Not a real Message-ID format.
    """
    import hashlib
    raw = f"{sender_email}:{date_str}"
    return "fallback-" + hashlib.md5(raw.encode()).hexdigest()[:12]
```

---

## 4. imap_poller.py — Complete Implementation

```python
# imap_poller.py
"""
Polls Gmail INBOX via IMAP4_SSL every IMAP_POLL_INTERVAL_SECONDS seconds.
Fetches all UNSEEN emails, parses each into EmailObject, marks as SEEN, yields to callback.

Design decisions:
- Uses imaplib.IMAP4_SSL (stdlib) — no third-party IMAP library
- Reconnects automatically on disconnect — network blips do not halt the system
- Runs inside asyncio via asyncio.to_thread() so it does not block the event loop
- The callback (agent loop) is called synchronously inside the polling coroutine
  before moving to the next email — one email processed at a time per poll cycle
"""

from __future__ import annotations

import asyncio
import imaplib
import time
from typing import Callable

from config import config
from email_parser import parse_email
from exceptions import EmailParseError, IMAPConnectionError
from logger import get_logger
from models import EmailObject

logger = get_logger(__name__)

# IMAP SEARCH command to find all unread emails in INBOX
IMAP_SEARCH_CRITERIA = "UNSEEN"

# How many consecutive connection failures before raising IMAPConnectionError
MAX_CONSECUTIVE_FAILURES = 5


class IMAPPoller:
    """
    Continuously polls Gmail INBOX for new (UNSEEN) emails.

    Usage:
        poller = IMAPPoller(callback=agent_loop.run)
        await poller.start()   # runs forever until cancelled

    Args:
        callback: Async or sync callable that receives (thread_id: str, email_obj: EmailObject).
                  Called once per parsed email in sequence.
    """

    def __init__(self, callback: Callable[[str, EmailObject], None]) -> None:
        self.callback = callback
        self._consecutive_failures = 0
        self._running = False

    async def start(self) -> None:
        """
        Start the polling loop. Runs indefinitely until self.stop() is called
        or MAX_CONSECUTIVE_FAILURES is reached.

        Raises:
            IMAPConnectionError: After MAX_CONSECUTIVE_FAILURES consecutive failures.
        """
        self._running = True
        logger.info("IMAP poller starting. Polling every %ds.", config.imap_poll_interval_seconds)

        while self._running:
            try:
                await asyncio.to_thread(self._poll_once)
                self._consecutive_failures = 0
            except IMAPConnectionError:
                raise   # re-raise fatal — max failures exceeded
            except Exception as exc:
                self._consecutive_failures += 1
                logger.error(
                    "IMAP poll error (attempt %d/%d): %s",
                    self._consecutive_failures,
                    MAX_CONSECUTIVE_FAILURES,
                    exc,
                    exc_info=True,
                )
                if self._consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    raise IMAPConnectionError(
                        f"IMAP poller failed {MAX_CONSECUTIVE_FAILURES} consecutive times. "
                        "Check Gmail credentials and network connectivity."
                    ) from exc

            await asyncio.sleep(config.imap_poll_interval_seconds)

    def stop(self) -> None:
        """Signal the polling loop to stop after the current cycle completes."""
        self._running = False
        logger.info("IMAP poller stop requested.")

    def _poll_once(self) -> None:
        """
        Execute one full poll cycle (synchronous — run in thread via asyncio.to_thread).

        Steps:
        1. Connect to imap.gmail.com:993 via IMAP4_SSL
        2. Login with GMAIL_ADDRESS and GMAIL_APP_PASSWORD
        3. SELECT INBOX (read-write mode so we can mark SEEN)
        4. SEARCH for UNSEEN message UIDs
        5. For each UID: FETCH full RFC822 content, parse, mark SEEN, call callback
        6. LOGOUT and close connection

        Note: A new IMAP connection is created per poll cycle.
        This avoids idle timeout issues common with long-lived IMAP connections.
        """
        mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)

        try:
            status, _ = mail.login(config.gmail_address, config.gmail_app_password)
            if status != "OK":
                raise imaplib.IMAP4.error(f"LOGIN returned: {status}")

            mail.select("INBOX")   # read-write — allows marking SEEN

            # SEARCH UNSEEN returns space-separated UID list as bytes
            status, data = mail.search(None, IMAP_SEARCH_CRITERIA)
            if status != "OK":
                logger.warning("IMAP SEARCH returned status: %s", status)
                return

            uid_list_bytes = data[0]
            if not uid_list_bytes:
                logger.debug("No UNSEEN emails found in INBOX.")
                return

            uid_list = uid_list_bytes.split()
            logger.info("Found %d UNSEEN email(s) to process.", len(uid_list))

            for uid in uid_list:
                self._fetch_and_process(mail, uid)

        finally:
            try:
                mail.logout()
            except Exception:
                pass   # best-effort logout

    def _fetch_and_process(self, mail: imaplib.IMAP4_SSL, uid: bytes) -> None:
        """
        Fetch one email by UID, parse it, mark as SEEN, and invoke callback.

        Args:
            mail: Active authenticated IMAP4_SSL connection with INBOX selected.
            uid:  Email UID bytes (e.g. b'42').

        The email is marked SEEN BEFORE calling the callback. This ensures that
        even if the callback raises, the email is not re-processed on the next poll.
        """
        # FETCH full RFC822 content (headers + body)
        status, msg_data = mail.fetch(uid, "(RFC822)")
        if status != "OK" or not msg_data or msg_data[0] is None:
            logger.warning("FETCH failed for UID %s — skipping.", uid)
            return

        # msg_data[0] is a tuple: (b'42 (RFC822 {12345}', b'<raw mime bytes>')
        raw_bytes: bytes = msg_data[0][1]

        # Mark as SEEN immediately — before any processing
        mail.store(uid, "+FLAGS", "\\Seen")

        try:
            email_obj = parse_email(raw_bytes)
        except EmailParseError as exc:
            logger.error("EmailParseError for UID %s: %s — skipping.", uid, exc)
            return

        logger.info(
            "Processing email from %s — subject: '%s'",
            email_obj["sender_email"],
            email_obj["subject"],
            extra={"thread_id": email_obj["thread_id"]},
        )

        # Invoke the agent loop callback
        try:
            self.callback(email_obj["thread_id"], email_obj)
        except Exception as exc:
            logger.error(
                "Callback error for thread %s: %s",
                email_obj["thread_id"],
                exc,
                exc_info=True,
                extra={"thread_id": email_obj["thread_id"]},
            )
            # Do not re-raise — one bad email must not crash the poller
```

---

## 5. smtp_sender.py — Complete Implementation

```python
# smtp_sender.py
"""
Sends outbound emails via Gmail SMTP (smtplib.SMTP_SSL).

Key behaviors:
- Always uses SMTP_SSL to smtp.gmail.com:465 (implicit TLS — more reliable than STARTTLS)
- Sets In-Reply-To and References headers to keep Gmail threading intact
- Appends AI disclaimer unconditionally via disclaimer.append_disclaimer()
- Creates a new SMTP connection per send call (avoids idle timeout on long-running agent)
- Retries once on SMTPException before raising SMTPConnectionError
"""

from __future__ import annotations

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate

from config import config
from disclaimer import append_disclaimer
from exceptions import SMTPConnectionError
from logger import get_logger

logger = get_logger(__name__)


def send_reply(
    to: str | list[str],
    subject: str,
    body: str,
    thread_id: str,
    in_reply_to: str = "",
    references: str = "",
    cc: list[str] | None = None,
) -> None:
    """
    Send an outbound email reply maintaining Gmail thread continuity.

    Args:
        to:           Recipient email address(es). Single string or list of strings.
        subject:      Email subject. Do NOT prepend 'Re:' — this function does not add it.
                      Use the original subject from the EmailObject unchanged.
        body:         Plain-text email body WITHOUT disclaimer. Disclaimer is appended here.
        thread_id:    The thread_id from AgentState. Used as the References header to keep
                      Gmail threading intact.
        in_reply_to:  The Message-ID of the email being replied to (from EmailObject.message_id).
                      Omit for proactive (non-reply) sends.
        references:   Space-separated References chain. Pass the original email's References
                      header + space + original message_id. If empty, thread_id is used.
        cc:           Optional list of CC addresses.

    Raises:
        SMTPConnectionError: If both the initial send and one retry fail.

    Note:
        The AI disclaimer is ALWAYS appended inside this function before sending.
        Callers must never add the disclaimer themselves.
    """
    if isinstance(to, str):
        to = [to]

    cc = cc or []
    final_body = append_disclaimer(body)

    msg = _build_mime_message(
        to=to,
        subject=subject,
        body=final_body,
        in_reply_to=in_reply_to,
        references=references if references else thread_id,
        cc=cc,
    )

    _send_with_retry(msg, to + cc)

    logger.info(
        "Sent reply to %s — subject: '%s'",
        ", ".join(to),
        subject,
        extra={"thread_id": thread_id},
    )


def _build_mime_message(
    to: list[str],
    subject: str,
    body: str,
    in_reply_to: str,
    references: str,
    cc: list[str],
) -> MIMEMultipart:
    """
    Construct the MIMEMultipart message with all required headers.

    Threading headers (In-Reply-To, References) are what Gmail uses to group
    emails into a single thread view. If these are missing or wrong, Gmail
    creates a new thread instead of continuing the existing one.

    Args:
        to:          List of To recipient addresses.
        subject:     Email subject string.
        body:        Full body text including disclaimer.
        in_reply_to: Message-ID of the parent email. Sets In-Reply-To header.
        references:  Full References chain. Sets References header.
        cc:          List of CC recipient addresses.

    Returns:
        MIMEMultipart: Fully assembled MIME message ready for smtplib.sendmail().
    """
    msg = MIMEMultipart("alternative")

    # Sender identity
    msg["From"] = formataddr(("MailMind Assistant", config.gmail_address))
    msg["To"] = ", ".join(to)
    msg["Date"] = formatdate(localtime=False)   # RFC 2822 UTC date
    msg["Subject"] = subject

    # Threading headers — REQUIRED for Gmail thread continuity
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
    if references:
        msg["References"] = references

    if cc:
        msg["Cc"] = ", ".join(cc)

    # Attach plain-text body
    msg.attach(MIMEText(body, "plain", "utf-8"))

    return msg


def _send_with_retry(msg: MIMEMultipart, all_recipients: list[str]) -> None:
    """
    Attempt to send the email. Retries once after 10 seconds on failure.

    Args:
        msg:             Fully assembled MIMEMultipart message.
        all_recipients:  Combined To + CC addresses for smtplib.sendmail().

    Raises:
        SMTPConnectionError: If both attempts fail.
    """
    for attempt in (1, 2):
        try:
            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
                smtp.ehlo()
                smtp.login(config.gmail_address, config.gmail_app_password)
                smtp.sendmail(
                    from_addr=config.gmail_address,
                    to_addrs=all_recipients,
                    msg=msg.as_string(),
                )
            return   # success — exit
        except smtplib.SMTPAuthenticationError as exc:
            # Auth failure is not retriable — wrong password
            raise SMTPConnectionError(
                f"SMTP authentication failed. Check GMAIL_APP_PASSWORD. Error: {exc}"
            ) from exc
        except smtplib.SMTPException as exc:
            if attempt == 1:
                logger.warning("SMTP send failed (attempt 1) — retrying in 10s: %s", exc)
                import time; time.sleep(10)
            else:
                raise SMTPConnectionError(
                    f"SMTP send failed after 2 attempts: {exc}"
                ) from exc
```

---

## 6. Gmail Threading Headers — Reference

| Header | Direction | What It Contains | Why It Matters |
|---|---|---|---|
| `Message-ID` | Inbound (read) | Unique ID of each email — e.g. `<abc123@mail.gmail.com>` | Used as `in_reply_to` in the next reply |
| `References` | Inbound (read) | Space-separated chain of all ancestor Message-IDs | First value = `thread_id` (session key) |
| `In-Reply-To` | Outbound (write) | Message-ID of the immediate parent email | Tells Gmail which email we're replying to |
| `References` | Outbound (write) | Full chain including the new reply's parent | Keeps the entire thread linked in Gmail |

**How thread_id is derived (exact logic):**
```
if References header exists:
    thread_id = References.split()[0]   # first Message-ID in chain = thread root
else:
    thread_id = Message-ID              # this IS the first email — it is the root
```

**How to reply preserving thread (exact header values to set):**
```
Given inbound email:
    message_id  = "<msg456@gmail.com>"
    references  = "<msg123@gmail.com> <msg456@gmail.com>"

Outbound reply headers:
    In-Reply-To = "<msg456@gmail.com>"       # the message we are replying to
    References  = "<msg123@gmail.com> <msg456@gmail.com> <msg456@gmail.com>"
                  # original references + space + the message we replied to
```

In `send_reply()`, the caller passes `in_reply_to=email_obj["message_id"]` and `references=email_obj.get("references", "") + " " + email_obj["message_id"]`. The agent loop is responsible for constructing these values from the stored `EmailObject`.

---

## 7. Data Flow

```
Gmail Inbox (imap.gmail.com:993)
    │
    │  IMAP4_SSL.search(None, "UNSEEN")
    │  IMAP4_SSL.fetch(uid, "(RFC822)")
    ▼
raw_bytes: bytes   ← complete MIME content of unseen email
    │
    │  email_parser.parse_email(raw_bytes)
    ├── email.message_from_bytes()
    ├── Extract: From, Date, Message-ID, References, In-Reply-To, Subject, To, Cc
    ├── _extract_plain_text()    ← prefers text/plain, skips text/html and attachments
    ├── _parse_date_header()     ← converts to UTC-aware datetime
    └── derive thread_id         ← References[0] or Message-ID
    │
    ▼
EmailObject (TypedDict)
    │
    │  imap_poller._fetch_and_process() calls:
    │  self.callback(email_obj["thread_id"], email_obj)
    ▼
agent/loop.py run(thread_id, email_obj)
    │
    │  ... agent processes email ...
    │
    │  tools/email_coordinator.send_reply(to, subject, body, thread_id)
    ▼
smtp_sender.send_reply()
    ├── append_disclaimer(body)    ← always appended here
    ├── _build_mime_message()      ← sets In-Reply-To + References for threading
    └── _send_with_retry()         ← SMTP_SSL to smtp.gmail.com:465
    │
    ▼
Gmail Sent (reply appears in same thread as original)
```

---

## 8. Error Handling

| Failure | Where Raised | What Happens |
|---|---|---|
| IMAP login authentication fails | `imap_poller._poll_once()` | `imaplib.IMAP4.error` caught, `_consecutive_failures` incremented, retry after poll interval |
| IMAP fetch returns non-OK status | `_fetch_and_process()` | Warning logged, UID skipped, poller continues with next UID |
| MIME parsing fails (malformed headers) | `email_parser.parse_email()` | `EmailParseError` raised, caught in `_fetch_and_process()`, email skipped with ERROR log |
| Email has no From header | `email_parser.parse_email()` | `EmailParseError` raised — From is required to determine sender |
| Email has no Date header | `email_parser.parse_email()` | `EmailParseError` raised — Date is required for temporal ordering |
| Body is empty (no text/plain part) | `_extract_plain_text()` | Returns `""` — not an error, agent handles empty body in `triage_node` |
| SMTP auth failure | `smtp_sender._send_with_retry()` | `SMTPConnectionError` raised immediately (no retry) — wrong password |
| SMTP send fails transiently | `smtp_sender._send_with_retry()` | Retries once after 10s — raises `SMTPConnectionError` if second fails |
| Agent callback raises exception | `imap_poller._fetch_and_process()` | ERROR logged with thread_id + traceback, poller continues with next email |
| 5 consecutive IMAP poll failures | `imap_poller.start()` | `IMAPConnectionError` raised — halts the poller, bubbles up to `main.py` |

---

## 9. Unit Tests — tests/test_email_parser.py

```python
# tests/test_email_parser.py
"""
Unit tests for email_parser.parse_email().
Run: pytest tests/test_email_parser.py -v
All tests use raw MIME bytes — no external connections.
"""

from __future__ import annotations

import email as email_lib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import pytest

from email_parser import parse_email
from exceptions import EmailParseError


def _make_raw(
    from_addr: str = "Alice <alice@example.com>",
    subject: str = "Team sync",
    body_plain: str = "Let's meet next week.",
    body_html: str | None = None,
    message_id: str = "<msg001@example.com>",
    date: str = "Mon, 04 Apr 2026 09:15:00 +0530",
    in_reply_to: str = "",
    references: str = "",
    to: str = "mailmind@gmail.com",
    cc: str = "",
) -> bytes:
    """Helper — builds a raw MIME email as bytes for test inputs."""
    if body_html:
        msg = MIMEMultipart("alternative")
        msg.attach(MIMEText(body_plain, "plain"))
        msg.attach(MIMEText(body_html, "html"))
    else:
        msg = MIMEText(body_plain, "plain")

    msg["From"] = from_addr
    msg["To"] = to
    msg["Subject"] = subject
    msg["Message-ID"] = message_id
    msg["Date"] = date
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
    if references:
        msg["References"] = references
    if cc:
        msg["Cc"] = cc

    return msg.as_bytes()


class TestPlainTextEmail:
    """Test case 1 — Simple plain-text email (first in a thread)."""

    def test_basic_fields_parsed_correctly(self):
        raw = _make_raw(
            from_addr="Alice <alice@example.com>",
            subject="Team sync",
            body_plain="Let's meet next week.",
            message_id="<root001@example.com>",
        )
        obj = parse_email(raw)

        assert obj["sender_email"] == "alice@example.com"
        assert obj["sender_name"] == "Alice"
        assert obj["subject"] == "Team sync"
        assert obj["body"] == "Let's meet next week."
        assert obj["message_id"] == "<root001@example.com>"

    def test_thread_id_equals_message_id_when_no_references(self):
        """First email in thread: no References → thread_id = Message-ID."""
        raw = _make_raw(message_id="<root001@example.com>", references="")
        obj = parse_email(raw)
        assert obj["thread_id"] == "<root001@example.com>"

    def test_timestamp_is_utc_aware(self):
        raw = _make_raw(date="Mon, 04 Apr 2026 09:15:00 +0530")
        obj = parse_email(raw)
        # +0530 offset: 09:15 IST = 03:45 UTC
        assert obj["timestamp"].tzinfo is not None
        assert obj["timestamp"].tzinfo == timezone.utc
        assert obj["timestamp"].hour == 3
        assert obj["timestamp"].minute == 45


class TestMultipartEmail:
    """Test case 2 — Multipart email with both text/plain and text/html parts."""

    def test_plain_text_preferred_over_html(self):
        raw = _make_raw(
            body_plain="Plain text content here.",
            body_html="<html><body><p>HTML content here.</p></body></html>",
        )
        obj = parse_email(raw)
        # Must return plain text, never HTML
        assert obj["body"] == "Plain text content here."
        assert "<html>" not in obj["body"]
        assert "<p>" not in obj["body"]


class TestReplyChainEmail:
    """Test case 3 — Email that is a reply in an existing thread."""

    def test_thread_id_is_first_reference_not_message_id(self):
        """Reply email: thread_id = first Message-ID in References header (the root)."""
        raw = _make_raw(
            message_id="<msg003@example.com>",
            in_reply_to="<msg002@example.com>",
            references="<root001@example.com> <msg002@example.com>",
        )
        obj = parse_email(raw)
        # thread_id must be the FIRST entry in References (root of thread)
        assert obj["thread_id"] == "<root001@example.com>"
        assert obj["message_id"] == "<msg003@example.com>"
        assert obj["in_reply_to"] == "<msg002@example.com>"

    def test_recipients_include_to_and_cc(self):
        raw = _make_raw(
            to="mailmind@gmail.com, bob@example.com",
            cc="charlie@example.com",
        )
        obj = parse_email(raw)
        assert "bob@example.com" in obj["recipients"]
        assert "charlie@example.com" in obj["recipients"]
        assert "mailmind@gmail.com" in obj["recipients"]

    def test_recipients_are_lowercase(self):
        raw = _make_raw(to="Bob@Example.COM")
        obj = parse_email(raw)
        assert "bob@example.com" in obj["recipients"]
        assert "Bob@Example.COM" not in obj["recipients"]


class TestMissingHeaders:
    """Test case 4 — Emails missing required headers (From, Date)."""

    def test_missing_from_raises_email_parse_error(self):
        # Build raw bytes manually without From header
        raw = (
            b"To: mailmind@gmail.com\r\n"
            b"Subject: No from\r\n"
            b"Date: Mon, 04 Apr 2026 09:15:00 +0000\r\n"
            b"Message-ID: <noform@example.com>\r\n"
            b"\r\n"
            b"Body here."
        )
        with pytest.raises(EmailParseError, match="From"):
            parse_email(raw)

    def test_missing_date_raises_email_parse_error(self):
        raw = (
            b"From: Alice <alice@example.com>\r\n"
            b"To: mailmind@gmail.com\r\n"
            b"Subject: No date\r\n"
            b"Message-ID: <nodate@example.com>\r\n"
            b"\r\n"
            b"Body here."
        )
        with pytest.raises(EmailParseError, match="Date"):
            parse_email(raw)

    def test_empty_body_returns_empty_string(self):
        """An email with no body must parse without error — body is empty string."""
        raw = _make_raw(body_plain="")
        obj = parse_email(raw)
        assert obj["body"] == ""
        assert isinstance(obj["body"], str)


class TestDisclaimerAppend:
    """Test case 5 — disclaimer.append_disclaimer behavior."""

    def test_disclaimer_is_appended(self):
        from disclaimer import append_disclaimer, DISCLAIMER_TEXT
        result = append_disclaimer("Hello, here is the meeting info.")
        assert result.endswith(DISCLAIMER_TEXT)

    def test_disclaimer_on_empty_body(self):
        from disclaimer import append_disclaimer, DISCLAIMER_TEXT
        result = append_disclaimer("")
        assert DISCLAIMER_TEXT in result

    def test_disclaimer_appears_exactly_once(self):
        from disclaimer import append_disclaimer, DISCLAIMER_TEXT
        body = "Some body text."
        result = append_disclaimer(body)
        assert result.count(DISCLAIMER_TEXT) == 1
```

---

## 10. Integration Checklist

Before Phase 2 is complete and Phase 3 can begin, every item must be true:

- [ ] `models.py` exists with `EmailObject` TypedDict — all 9 fields present with types
- [ ] `disclaimer.py` exists — `DISCLAIMER_TEXT` constant and `append_disclaimer(body: str) -> str` implemented
- [ ] `email_parser.py` exists — `parse_email(raw_bytes: bytes) -> EmailObject` implemented
- [ ] `imap_poller.py` exists — `IMAPPoller` class with `start()`, `stop()`, `_poll_once()`, `_fetch_and_process()`
- [ ] `smtp_sender.py` exists — `send_reply(to, subject, body, thread_id, ...)` implemented
- [ ] `disclaimer.append_disclaimer()` is called inside `smtp_sender.send_reply()` — no bypass possible
- [ ] `In-Reply-To` and `References` headers are set on every outbound MIME message
- [ ] IMAP marks emails as `\Seen` BEFORE calling the callback (prevents re-processing)
- [ ] `imap_poller._fetch_and_process()` catches `EmailParseError` and skips the email without crashing
- [ ] `imap_poller.start()` catches callback exceptions and continues polling
- [ ] `smtp_sender._send_with_retry()` retries exactly once on `SMTPException`, raises `SMTPConnectionError` on second failure
- [ ] `smtp_sender._send_with_retry()` does NOT retry on `SMTPAuthenticationError` (not retriable)
- [ ] `pytest tests/test_email_parser.py -v` passes all tests with no warnings
- [ ] Running the poller manually with a real test email processes it end-to-end (check logs for "Processing email")
- [ ] Sending a test reply via `send_reply()` with real credentials appears in Gmail thread correctly grouped

---

## Cross-Phase References

| What | Exported From | Imported By |
|---|---|---|
| `EmailObject` TypedDict | `models.py` | `agent/loop.py` (P6), `agent/nodes.py` (P6), `tool_registry.py` (P5), `imap_poller.py` (P2), `email_parser.py` (P2) |
| `parse_email()` | `email_parser.py` | `imap_poller.py` (P2) |
| `send_reply()` | `smtp_sender.py` | `tools/email_coordinator.py` (P5) — all outbound emails go through here |
| `append_disclaimer()` | `disclaimer.py` | `smtp_sender.py` (P2) only — no other caller |
| `IMAPPoller` | `imap_poller.py` | `main.py` (P7) — instantiated once, started in asyncio loop |
| `IMAPConnectionError` | `exceptions.py` (P1) | `imap_poller.py`, `main.py` |
| `SMTPConnectionError` | `exceptions.py` (P1) | `smtp_sender.py`, `tools/email_coordinator.py` |
| `EmailParseError` | `exceptions.py` (P1) | `email_parser.py`, `imap_poller.py` |

---

*PHASE2_IMAP_SMTP.md | Team TRIOLOGY | PCCOE Pune | Problem Statement 03*
