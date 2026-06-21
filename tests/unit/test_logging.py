"""Tests for structured logging."""

from __future__ import annotations

import logging

from fxfill_banking_agent.logging import configure_logging, get_logger


class TestLogging:
    def test_configure_development(self) -> None:
        configure_logging(level=logging.DEBUG, json_format=False)

    def test_configure_json(self) -> None:
        configure_logging(level=logging.WARNING, json_format=True)

    def test_get_logger_returns_bound_logger(self) -> None:
        logger = get_logger("test.module")
        assert logger is not None
        logger.info("test_message", key="value")

    def test_get_logger_default_name(self) -> None:
        logger = get_logger()
        assert logger is not None
