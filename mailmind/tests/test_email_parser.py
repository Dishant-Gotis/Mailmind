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
        raw = _make_raw(message_id="<root001@example.com>", references="")
        obj = parse_email(raw)
        assert obj["thread_id"] == "<root001@example.com>"

    def test_timestamp_is_utc_aware(self):
        raw = _make_raw(date="Mon, 04 Apr 2026 09:15:00 +0530")
        obj = parse_email(raw)
        assert obj["timestamp"].tzinfo is not None
        assert obj["timestamp"].tzinfo == timezone.utc
        assert obj["timestamp"].hour == 3
        assert obj["timestamp"].minute == 45


class TestMultipartEmail:
    def test_plain_text_preferred_over_html(self):
        raw = _make_raw(
            body_plain="Plain text content here.",
            body_html="<html><body><p>HTML content here.</p></body></html>",
        )
        obj = parse_email(raw)
        assert obj["body"] == "Plain text content here."
        assert "<html>" not in obj["body"]
        assert "<p>" not in obj["body"]


class TestReplyChainEmail:
    def test_thread_id_is_first_reference_not_message_id(self):
        raw = _make_raw(
            message_id="<msg003@example.com>",
            in_reply_to="<msg002@example.com>",
            references="<root001@example.com> <msg002@example.com>",
        )
        obj = parse_email(raw)
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
    def test_missing_from_raises_email_parse_error(self):
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
        raw = _make_raw(body_plain="")
        obj = parse_email(raw)
        assert obj["body"] == ""
        assert isinstance(obj["body"], str)


class TestDisclaimerAppend:
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
