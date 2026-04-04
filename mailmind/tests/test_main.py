"""Tests for main.py orchestration flow."""

from __future__ import annotations

import asyncio
import signal
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from exceptions import ConfigurationError, IMAPConnectionError


class _DummyPoller:
    def __init__(self, callback):
        self.callback = callback
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True


async def _pending_poller(_poller) -> None:
    await asyncio.sleep(3600)


async def _fatal_poller(_poller) -> None:
    raise IMAPConnectionError("fatal poll failure")


def _make_cfg(vip_emails: list[str] | None = None):
    return SimpleNamespace(
        gmail_address="mailmind@example.com",
        openrouter_model="google/gemini-2.0-flash-lite-preview-02-05:free",
        imap_poll_interval_seconds=30,
        vip_emails=vip_emails or [],
    )


def test_main_successful_startup_and_shutdown():
    import main as main_module

    cfg = _make_cfg(vip_emails=["vip@example.com"])

    with patch("config.load_config", return_value=cfg), patch.object(
        main_module, "init_db"
    ) as mock_init_db, patch("preference_store.seed_vip_list") as mock_seed, patch(
        "calendar_auth.get_calendar_service"
    ) as mock_calendar, patch("imap_poller.IMAPPoller", _DummyPoller), patch.object(
        main_module, "_run_poller", new=_pending_poller
    ), patch.object(
        main_module, "_register_signal_handlers", side_effect=lambda _loop, cb: cb()
    ):
        asyncio.run(main_module.main())

    mock_init_db.assert_called_once()
    mock_seed.assert_called_once_with(["vip@example.com"])
    mock_calendar.assert_called_once()


def test_main_exits_on_configuration_error():
    import main as main_module

    with patch("config.load_config", side_effect=ConfigurationError("bad config")):
        with pytest.raises(SystemExit) as exc_info:
            asyncio.run(main_module.main())

    assert exc_info.value.code == 1


def test_main_exits_on_calendar_auth_failure():
    import main as main_module

    cfg = _make_cfg(vip_emails=[])

    with patch("config.load_config", return_value=cfg), patch.object(
        main_module, "init_db"
    ), patch("calendar_auth.get_calendar_service", side_effect=RuntimeError("oauth failed")):
        with pytest.raises(SystemExit) as exc_info:
            asyncio.run(main_module.main())

    assert exc_info.value.code == 1


def test_main_exits_when_poller_fails_fatally():
    import main as main_module

    cfg = _make_cfg(vip_emails=[])

    with patch("config.load_config", return_value=cfg), patch.object(
        main_module, "init_db"
    ), patch("calendar_auth.get_calendar_service"), patch(
        "imap_poller.IMAPPoller", _DummyPoller
    ), patch.object(
        main_module, "_run_poller", new=_fatal_poller
    ), patch.object(
        main_module, "_register_signal_handlers", side_effect=lambda _loop, _cb: None
    ):
        with pytest.raises(SystemExit) as exc_info:
            asyncio.run(main_module.main())

    assert exc_info.value.code == 1


def test_register_signal_handlers_falls_back_to_signal_module():
    import main as main_module

    class _FakeLoop:
        def add_signal_handler(self, _sig, _handler):
            raise NotImplementedError

    with patch("signal.signal") as mock_signal:
        main_module._register_signal_handlers(_FakeLoop(), lambda: None)

    called_signals = [call.args[0] for call in mock_signal.call_args_list]
    assert signal.SIGINT in called_signals
    assert signal.SIGTERM in called_signals
