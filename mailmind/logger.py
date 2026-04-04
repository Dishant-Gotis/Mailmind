"""Structured logger for MailMind."""

import logging
import sys

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)-30s | %(thread_id_tag)s%(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class ThreadIDFilter(logging.Filter):
    """Injects thread_id_tag into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        thread_id = getattr(record, "thread_id", None)
        record.thread_id_tag = f"[{thread_id}] " if thread_id else ""
        return True


def get_logger(name: str, level: int = logging.DEBUG) -> logging.Logger:
    """Return a named logger configured with the MailMind log format."""
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    logger.setLevel(level)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)

    formatter = logging.Formatter(fmt=LOG_FORMAT, datefmt=DATE_FORMAT)
    handler.setFormatter(formatter)

    thread_filter = ThreadIDFilter()
    handler.addFilter(thread_filter)
    logger.addFilter(thread_filter)

    logger.addHandler(handler)
    logger.propagate = False

    return logger


root_logger = get_logger("mailmind")
