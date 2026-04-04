"""
Sends outbound emails via Gmail SMTP (smtplib.SMTP_SSL).
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
    if isinstance(to, str):
        to = [to]

    own_address = config.gmail_address.lower()
    cc = [
        addr for addr in (cc or [])
        if addr.lower() != own_address and addr.lower() not in (t.lower() for t in to)
    ]
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
    msg = MIMEMultipart("alternative")

    msg["From"] = formataddr(("MailMind Assistant", config.gmail_address))
    msg["To"] = ", ".join(to)
    msg["Date"] = formatdate(localtime=False)
    msg["Subject"] = subject

    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
    if references:
        msg["References"] = references

    if cc:
        msg["Cc"] = ", ".join(cc)

    msg.attach(MIMEText(body, "plain", "utf-8"))

    return msg


def _send_with_retry(msg: MIMEMultipart, all_recipients: list[str]) -> None:
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
            return
        except smtplib.SMTPAuthenticationError as exc:
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
