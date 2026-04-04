from __future__ import annotations

from pathlib import Path

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from exceptions import ConfigurationError


class Config(BaseSettings):
    """Central configuration for MailMind loaded from .env."""

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

    # ── OpenRouter LLM ─────────────────────────────────────────────────────────
    openrouter_api_key: str
    openrouter_model: str = "google/gemini-2.0-flash-lite-preview-02-05:free"
    llm_confidence_threshold: float = 0.7

    # ── Google Calendar ────────────────────────────────────────────────────────
    google_calendar_credentials_path: str = "credentials.json"
    google_calendar_token_path: str = "data/token.json"

    # ── Agent Behaviour ────────────────────────────────────────────────────────
    attendance_threshold: float = 0.5
    meeting_duration_minutes: int = 60

    # ── VIP ────────────────────────────────────────────────────────────────────
    vip_email_list: str = ""   # comma-separated, empty string = no VIPs

    # ── Derived properties ─────────────────────────────────────────────────────

    @property
    def vip_emails(self) -> list[str]:
        """Parse VIP_EMAIL_LIST into a cleaned list of lowercase email strings."""
        if not self.vip_email_list.strip():
            return []
        return [email.strip().lower() for email in self.vip_email_list.split(",") if email.strip()]

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
    def validate_gmail_address(cls, value: str) -> str:
        if "@" not in value or "." not in value.split("@")[-1]:
            raise ValueError(
                f"GMAIL_ADDRESS '{value}' does not look like a valid email address. "
                "Set a valid Gmail address in your .env file."
            )
        return value.lower().strip()

    @field_validator("gmail_app_password")
    @classmethod
    def validate_app_password(cls, value: str) -> str:
        cleaned = value.replace("-", "").replace(" ", "")
        if len(cleaned) != 16:
            raise ValueError(
                "GMAIL_APP_PASSWORD appears invalid (expected 16 chars after removing dashes, "
                f"got {len(cleaned)}). Generate a new App Password at: "
                "myaccount.google.com -> Security -> App passwords."
            )
        return value

    @field_validator("llm_confidence_threshold")
    @classmethod
    def validate_confidence_threshold(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError(
                f"LLM_CONFIDENCE_THRESHOLD must be between 0.0 and 1.0, got {value}."
            )
        return value

    @field_validator("attendance_threshold")
    @classmethod
    def validate_attendance_threshold(cls, value: float) -> float:
        if not 0.0 < value <= 1.0:
            raise ValueError(
                "ATTENDANCE_THRESHOLD must be between 0.0 (exclusive) and 1.0 (inclusive), "
                f"got {value}."
            )
        return value

    @field_validator("imap_poll_interval_seconds")
    @classmethod
    def validate_poll_interval(cls, value: int) -> int:
        if value < 10:
            raise ValueError(
                "IMAP_POLL_INTERVAL_SECONDS must be at least 10 seconds to avoid Gmail "
                f"rate limiting, got {value}."
            )
        return value

    @model_validator(mode="after")
    def validate_credentials_file_exists(self) -> "Config":
        creds_path = Path(self.google_calendar_credentials_path)
        if not creds_path.exists():
            raise ValueError(
                f"GOOGLE_CALENDAR_CREDENTIALS_PATH points to '{creds_path}' which does not exist. "
                "Download credentials.json from Google Cloud Console -> APIs & Services -> Credentials."
            )
        return self


def load_config() -> Config:
    """Load and validate config, wrapping failures in ConfigurationError."""
    try:
        return Config()
    except Exception as exc:  # pragma: no cover - exercised through startup and tests
        raise ConfigurationError(
            f"MailMind configuration error:\n\n{exc}\n\n"
            "Fix the above issue in your .env file, then restart."
        ) from exc


config: Config = load_config()
