"""Structured logging to stderr (structlog). JSON for machines, key=value for people.

Log events carry counts, hashes, page numbers and timings. Never report text, and never a secret.
"""

from __future__ import annotations

import logging
import sys

import structlog


def configure_logging(fmt: str = "console", level: str = "WARNING") -> None:
    renderer: structlog.typing.Processor = (
        structlog.processors.JSONRenderer()
        if fmt == "json"
        else structlog.dev.ConsoleRenderer(colors=False)
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelNamesMapping().get(level, logging.WARNING)
        ),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=False,
    )
