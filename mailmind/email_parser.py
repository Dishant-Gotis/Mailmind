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
    if not sender_email or "@" not in sender_email:
        import re
        matches = re.findall(r'[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}', from_header)
        if matches:
            sender_email = matches[-1].lower()
        else:
            raise EmailParseError(f"Cannot extract valid email from From header: {from_header!r}")
            
    sender_email = sender_email.lower().strip()
    sender_name = sender_name.strip()

    # ── Parse Message-ID ───────────────────────────────────────────────────────
    message_id = msg.get("Message-ID", "").strip()

    # ── Derive thread_id from References header ────────────────────────────────
    references_header = msg.get("References", "").strip()
    if references_header:
        all_refs = references_header.split()
        from checkpointer import find_thread_by_any_ref
        existing_tid = find_thread_by_any_ref(all_refs)
        thread_id = existing_tid if existing_tid else all_refs[0].strip()
    else:
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
    collected: list[str] = []
    html_payload: str = ""

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            disposition = part.get("Content-Disposition", "")

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
            elif content_type == "text/html" and not html_payload:
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    try:
                        html_payload = payload.decode(charset, errors="replace")
                    except Exception:
                        html_payload = payload.decode("utf-8", errors="replace")
    else:
        content_type = msg.get_content_type()
        if content_type == "text/plain":
            payload = msg.get_payload(decode=True)
            if payload:
                charset = msg.get_content_charset() or "utf-8"
                collected.append(payload.decode(charset, errors="replace"))
        elif content_type == "text/html":
            payload = msg.get_payload(decode=True)
            if payload:
                charset = msg.get_content_charset() or "utf-8"
                html_payload = payload.decode(charset, errors="replace")

    plain_text = "\n".join(collected).strip()
    if not plain_text and html_payload:
        import html as html_lib
        import re
        body = re.sub(r"<[^>]+>", " ", html_payload)
        body = html_lib.unescape(body)
        plain_text = " ".join(body.split())
        
    return plain_text


def _parse_date_header(date_str: str) -> datetime:
    try:
        dt = email.utils.parsedate_to_datetime(date_str)
        if dt.tzinfo is not None:
            return dt.astimezone(timezone.utc)
        else:
            return dt.replace(tzinfo=timezone.utc)
    except Exception:
        logger.warning(f"Failed to parse Date header: '{date_str}' — using current UTC time.")
        return datetime.now(timezone.utc)


def _generate_fallback_id(sender_email: str, date_str: str) -> str:
    import hashlib
    raw = f"{sender_email}:{date_str}"
    return "fallback-" + hashlib.md5(raw.encode()).hexdigest()[:12]
