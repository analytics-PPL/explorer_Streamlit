"""Centralised logging configuration for the neighbourhood explorer."""

from __future__ import annotations

import logging
import sys


def configure_logging(*, level: int = logging.INFO) -> None:
    """Set up a consistent logging format across the application.

    Call once at application startup (e.g. in Home.py).
    """
    root = logging.getLogger()
    if root.handlers:
        return

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    root.addHandler(handler)
    root.setLevel(level)

    # Suppress noisy third-party loggers
    for noisy in ("urllib3", "streamlit", "watchdog", "fsevents"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
