"""Structured logging for the banking agent.

Uses ``structlog`` to emit JSON logs with consistent keys. In development
logs go to stderr; in production they can be routed to a collector.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog


def configure_logging(
    level: int = logging.INFO,
    json_format: bool = False,
) -> None:
    """Set up structured logging for the agent runtime.

    Args:
        level: Minimum log level.
        json_format: When True, emit JSON lines (production). When
            False, emit coloured console output (development).

    Must be called once at process start, before any agent runs.
    """
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
    ]

    if json_format:
        structlog.configure(
            processors=shared_processors
            + [
                structlog.processors.dict_tracebacks,
                structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(level),
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(sys.stderr),
            cache_logger_on_first_use=True,
        )
    else:
        structlog.configure(
            processors=shared_processors
            + [
                structlog.dev.ConsoleRenderer(),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(level),
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(sys.stderr),
            cache_logger_on_first_use=True,
        )

    # Route stdlib logging through structlog
    logging.basicConfig(format="%(message)s", stream=sys.stderr, level=level)


def get_logger(name: str | None = None) -> structlog.BoundLogger:
    """Return a bound logger for the given module name."""
    return structlog.get_logger(name or __name__)  # type: ignore[no-any-return]
