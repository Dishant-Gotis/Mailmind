from __future__ import annotations

import imaplib
import smtplib
import sys
from typing import Callable

try:
    from config import config
except Exception as exc:
    print(f"\nFATAL: Configuration loading failed\n{exc}\n")
    print("Fix the above errors in your .env file, then re-run setup.py.")
    sys.exit(1)

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from openai import OpenAI

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]


def check_config() -> None:
    required = {
        "gmail_address": config.gmail_address,
        "gmail_app_password": config.gmail_app_password,
        "openrouter_api_key": config.openrouter_api_key,
        "google_calendar_credentials_path": config.google_calendar_credentials_path,
    }
    for key, value in required.items():
        if not str(value).strip():
            raise ValueError(f"{key} is empty.")


def check_imap() -> None:
    client = imaplib.IMAP4_SSL("imap.gmail.com")
    try:
        client.login(config.gmail_address, config.gmail_app_password)
        client.select("INBOX")
    finally:
        try:
            client.logout()
        except Exception:
            pass


def check_smtp() -> None:
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as server:
        server.login(config.gmail_address, config.gmail_app_password)


def check_llm() -> None:
    client = OpenAI(
        api_key=config.openrouter_api_key,
        base_url="https://openrouter.ai/api/v1",
    )
    response = client.chat.completions.create(
        model=config.openrouter_model,
        messages=[{"role": "user", "content": "Reply with exactly: OK"}],
        temperature=0,
        max_tokens=8,
    )
    content = ""
    if response.choices:
        content = (response.choices[0].message.content or "").strip()
    if not content:
        raise RuntimeError("OpenRouter API returned an empty response body.")


def check_google_calendar() -> None:
    creds = None
    token_path = config.calendar_token_path

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            print("\n     No valid token - opening browser for OAuth authorization...")
            print("     Sign in to the MailMind Gmail account and click Allow.")
            flow = InstalledAppFlow.from_client_secrets_file(
                str(config.calendar_credentials_path), SCOPES
            )
            creds = flow.run_local_server(port=0)
            print("     Authorization complete.")
        token_path.write_text(creds.to_json(), encoding="utf-8")
        print(f"     Token saved to: {token_path}")

    service = build("calendar", "v3", credentials=creds)
    # Instead of requesting the whole calendar (which needs full calendar scope),
    # we just list 1 event to prove the calendar.events scope works perfectly.
    events_result = service.events().list(calendarId="primary", maxResults=1).execute()
    if not isinstance(events_result, dict):
        raise RuntimeError("Unable to access Google Calendar primary calendar events.")


def run_check(step: int, total: int, name: str, fn: Callable[[], None]) -> bool:
    print(f"[{step}/{total}] {name:<30}", end=" ")
    try:
        fn()
        print("[PASS]")
        return True
    except Exception as exc:
        print("[FAIL]")
        print(f"      {type(exc).__name__}: {exc}")
        return False


def main() -> int:
    checks = [
        ("Configuration", check_config),
        ("IMAP Connection", check_imap),
        ("SMTP Connection", check_smtp),
        ("OpenRouter LLM", check_llm),
        ("Google Calendar", check_google_calendar),
    ]

    print("\n" + "=" * 60)
    print("  MAILMIND SETUP VALIDATOR")
    print("  Running all connection checks independently...")
    print("=" * 60)

    passed = 0
    total = len(checks)

    for idx, (name, fn) in enumerate(checks, start=1):
        if run_check(idx, total, name, fn):
            passed += 1

    failed = total - passed
    print("-" * 60)
    print(f"  Passed: {passed}/{total}   Failed: {failed}/{total}")
    print("=" * 60)

    if failed == 0:
        print("\n  [PASS] All checks passed. Run: python main.py\n")
    else:
        print(f"\n  [FAIL] {failed} check(s) failed. Fix the issues above before running main.py.\n")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
