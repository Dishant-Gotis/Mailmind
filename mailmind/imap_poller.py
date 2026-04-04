"""
Polls Gmail INBOX via IMAP4_SSL every IMAP_POLL_INTERVAL_SECONDS seconds.
Fetches all UNSEEN emails, parses each into EmailObject, marks as SEEN, yields to callback.
"""

from __future__ import annotations

import asyncio
import imaplib
from typing import Callable

from config import config
from email_parser import parse_email
from exceptions import EmailParseError, IMAPConnectionError
from logger import get_logger
from models import EmailObject

logger = get_logger(__name__)

IMAP_SEARCH_CRITERIA = "UNSEEN"
MAX_CONSECUTIVE_FAILURES = 5


class IMAPPoller:
    def __init__(self, callback: Callable[[str, EmailObject], None]) -> None:
        self.callback = callback
        self._consecutive_failures = 0
        self._running = False

    async def start(self) -> None:
        self._running = True
        logger.info("IMAP poller starting. Polling every %ds.", config.imap_poll_interval_seconds)

        while self._running:
            try:
                await asyncio.to_thread(self._poll_once)
                self._consecutive_failures = 0
            except IMAPConnectionError:
                raise
            except Exception as exc:
                self._consecutive_failures += 1
                logger.error(
                    "IMAP poll error (attempt %d/%d): %s",
                    self._consecutive_failures,
                    MAX_CONSECUTIVE_FAILURES,
                    exc,
                )
                if self._consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    raise IMAPConnectionError(
                        f"IMAP poller failed {MAX_CONSECUTIVE_FAILURES} consecutive times."
                    ) from exc

            await asyncio.sleep(config.imap_poll_interval_seconds)

    def stop(self) -> None:
        self._running = False
        logger.info("IMAP poller stop requested.")

    def _poll_once(self) -> None:
        mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)

        try:
            status, _ = mail.login(config.gmail_address, config.gmail_app_password)
            if status != "OK":
                raise imaplib.IMAP4.error(f"LOGIN returned: {status}")

            mail.select("INBOX")

            status, data = mail.search(None, IMAP_SEARCH_CRITERIA)
            if status != "OK":
                return

            uid_list_bytes = data[0]
            if not uid_list_bytes:
                return

            uid_list = uid_list_bytes.split()
            logger.info("Found %d UNSEEN email(s) to process.", len(uid_list))

            for uid in uid_list:
                self._fetch_and_process(mail, uid)

        finally:
            try:
                mail.logout()
            except Exception:
                pass

    def _fetch_and_process(self, mail: imaplib.IMAP4_SSL, uid: bytes) -> None:
        status, msg_data = mail.fetch(uid, "(RFC822)")
        if status != "OK" or not msg_data or msg_data[0] is None:
            return

        raw_bytes: bytes = msg_data[0][1]
        mail.store(uid, "+FLAGS", "\\Seen")

        try:
            email_obj = parse_email(raw_bytes)
        except EmailParseError as exc:
            logger.error("EmailParseError for UID %s: %s", uid, exc)
            return

        from config import config
        if email_obj["sender_email"].lower() == config.gmail_address.lower():
            logger.debug(
                "Skipping own email (sender=%s, thread=%s)",
                email_obj["sender_email"], email_obj["thread_id"],
            )
            return

        try:
            self.callback(email_obj["thread_id"], email_obj)
        except Exception as exc:
            logger.error(
                "Callback error for thread %s: %s",
                email_obj["thread_id"],
                exc,
            )
