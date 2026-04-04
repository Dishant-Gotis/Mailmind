"""Tests for config.py validation logic."""

import os
from unittest.mock import patch

import pytest


class TestConfigValidation:
    """Tests that Config validates expected values and rejects invalid ones."""

    def _make_valid_env(self, **overrides) -> dict:
        base = {
            "GMAIL_ADDRESS": "test@gmail.com",
            "GMAIL_APP_PASSWORD": "abcd-efgh-ijkl-mnop",
            "OPENROUTER_API_KEY": "AIzaSyTest12345",
            "GOOGLE_CALENDAR_CREDENTIALS_PATH": "credentials.json",
            "IMAP_POLL_INTERVAL_SECONDS": "30",
            "ATTENDANCE_THRESHOLD": "0.5",
            "LLM_CONFIDENCE_THRESHOLD": "0.7",
        }
        base.update(overrides)
        return base

    def test_valid_config_loads_without_error(self, tmp_path):
        creds = tmp_path / "credentials.json"
        creds.write_text("{}", encoding="utf-8")

        env = self._make_valid_env(GOOGLE_CALENDAR_CREDENTIALS_PATH=str(creds))
        with patch.dict(os.environ, env, clear=True):
            from config import Config

            cfg = Config(_env_file=None)
            assert cfg.gmail_address == "test@gmail.com"

    def test_missing_gmail_address_raises(self):
        env = self._make_valid_env()
        del env["GMAIL_ADDRESS"]

        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(Exception):
                from config import Config

                Config(_env_file=None)

    def test_invalid_email_format_raises(self, tmp_path):
        creds = tmp_path / "credentials.json"
        creds.write_text("{}", encoding="utf-8")

        env = self._make_valid_env(
            GMAIL_ADDRESS="notanemail",
            GOOGLE_CALENDAR_CREDENTIALS_PATH=str(creds),
        )
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(Exception) as exc_info:
                from config import Config

                Config(_env_file=None)

            assert "GMAIL_ADDRESS" in str(exc_info.value) or "email" in str(exc_info.value).lower()

    def test_short_app_password_raises(self, tmp_path):
        creds = tmp_path / "credentials.json"
        creds.write_text("{}", encoding="utf-8")

        env = self._make_valid_env(
            GMAIL_APP_PASSWORD="tooshort",
            GOOGLE_CALENDAR_CREDENTIALS_PATH=str(creds),
        )
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(Exception) as exc_info:
                from config import Config

                Config(_env_file=None)

            assert "App Password" in str(exc_info.value) or "password" in str(exc_info.value).lower()

    def test_confidence_threshold_out_of_range_raises(self, tmp_path):
        creds = tmp_path / "credentials.json"
        creds.write_text("{}", encoding="utf-8")

        env = self._make_valid_env(
            LLM_CONFIDENCE_THRESHOLD="1.5",
            GOOGLE_CALENDAR_CREDENTIALS_PATH=str(creds),
        )
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(Exception):
                from config import Config

                Config(_env_file=None)

    def test_vip_emails_property_parses_correctly(self, tmp_path):
        creds = tmp_path / "credentials.json"
        creds.write_text("{}", encoding="utf-8")

        env = self._make_valid_env(
            VIP_EMAIL_LIST="CEO@Company.com, CTO@Company.com",
            GOOGLE_CALENDAR_CREDENTIALS_PATH=str(creds),
        )
        with patch.dict(os.environ, env, clear=True):
            from config import Config

            cfg = Config(_env_file=None)
            assert cfg.vip_emails == ["ceo@company.com", "cto@company.com"]

    def test_empty_vip_list_returns_empty(self, tmp_path):
        creds = tmp_path / "credentials.json"
        creds.write_text("{}", encoding="utf-8")

        env = self._make_valid_env(
            VIP_EMAIL_LIST="",
            GOOGLE_CALENDAR_CREDENTIALS_PATH=str(creds),
        )
        with patch.dict(os.environ, env, clear=True):
            from config import Config

            cfg = Config(_env_file=None)
            assert cfg.vip_emails == []

    def test_missing_credentials_json_raises(self):
        env = self._make_valid_env(
            GOOGLE_CALENDAR_CREDENTIALS_PATH="/nonexistent/path/credentials.json"
        )
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(Exception) as exc_info:
                from config import Config

                Config(_env_file=None)

            assert "credentials.json" in str(exc_info.value)
