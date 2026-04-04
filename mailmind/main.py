"""
MailMind runtime entrypoint.

Run with:
    python main.py
"""

from __future__ import annotations

import asyncio
import signal
import sys
from collections.abc import Callable

from db import init_db
from exceptions import ConfigurationError, IMAPConnectionError
from logger import get_logger

logger = get_logger(__name__)

BANNER = """
========================================
               MAILMIND
      Autonomous Scheduling Agent
========================================
"""


def _register_signal_handlers(loop: asyncio.AbstractEventLoop, on_shutdown: Callable[[], None]) -> None:
    """
    Register SIGINT/SIGTERM handlers with a Windows-safe fallback.
    """
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, on_shutdown)
        except NotImplementedError:
            # For Windows, signal handlers registered with signal.signal
            # can be tricky. We'll use a wrapper.
            def windows_handler(_signum, _frame):
                # Using call_soon_threadsafe to ensure we set the event in the right thread
                loop.call_soon_threadsafe(on_shutdown)
            signal.signal(sig, windows_handler)


async def _run_poller(poller) -> None:
    """
    Start IMAP polling and bubble up fatal errors.
    """
    try:
        await poller.start()
    except asyncio.CancelledError:
        logger.info("IMAP poller task cancelled.")
        raise


async def main() -> None:
    """
    Orchestrate startup, background processing, and graceful shutdown.
    """
    print(BANNER)

    logger.info("Loading configuration...")
    try:
        from config import load_config

        cfg = load_config()
        logger.info("Gmail address: %s", cfg.gmail_address)
        logger.info("OpenRouter model: %s", cfg.openrouter_model)
        logger.info("IMAP poll interval: %ds", cfg.imap_poll_interval_seconds)
    except ConfigurationError as exc:
        logger.critical("Configuration error: %s", exc)
        sys.exit(1)

    logger.info("Initialising database...")
    try:
        init_db()
    except Exception as exc:
        logger.critical("Database init failed: %s", exc)
        sys.exit(1)

    from preference_store import seed_vip_list

    if cfg.vip_emails:
        seed_vip_list(cfg.vip_emails)
        logger.info("VIP list seeded: %d address(es).", len(cfg.vip_emails))

    logger.info("Validating Google Calendar credentials...")
    try:
        from calendar_auth import get_calendar_service

        get_calendar_service()
        logger.info("Google Calendar: OK")
    except Exception as exc:
        logger.critical("Google Calendar auth failed: %s", exc)
        logger.critical("Run 'python setup.py' to complete the OAuth flow.")
        sys.exit(1)

    from agent.loop import run as agent_run
    from imap_poller import IMAPPoller

    logger.info("Starting IMAP poller for %s...", cfg.gmail_address)
    poller = IMAPPoller(callback=agent_run)
    poller_task = asyncio.create_task(_run_poller(poller), name="imap-poller")

    shutdown_event = asyncio.Event()

    def _handle_shutdown() -> None:
        logger.info("Shutdown signal received.")
        shutdown_event.set()

    loop = asyncio.get_running_loop()
    _register_signal_handlers(loop, _handle_shutdown)

    logger.info("MailMind is running. Press Ctrl+C to stop.")

    shutdown_wait_task = asyncio.create_task(shutdown_event.wait(), name="shutdown-wait")
    done, _pending = await asyncio.wait(
        {poller_task, shutdown_wait_task},
        return_when=asyncio.FIRST_COMPLETED,
    )

    exit_code = 0
    if poller_task in done:
        exc = poller_task.exception()
        if isinstance(exc, IMAPConnectionError):
            logger.critical("IMAP fatal error: %s", exc)
            exit_code = 1
        elif exc is not None:
            logger.critical("Unexpected poller failure: %s", exc)
            exit_code = 1

    logger.info("Shutting down...")
    poller.stop()

    if not poller_task.done():
        poller_task.cancel()
    if not shutdown_wait_task.done():
        shutdown_wait_task.cancel()

    await asyncio.gather(poller_task, shutdown_wait_task, return_exceptions=True)
    logger.info("MailMind stopped cleanly.")

    if exit_code != 0:
        sys.exit(exit_code)


if __name__ == "__main__":
    asyncio.run(main())
