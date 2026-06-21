"""Tests for typed configuration models."""

from __future__ import annotations

import pytest

from fxfill_banking_agent.config import (
    AgentConfig,
    DatabaseConfig,
    Environment,
    LLMConfig,
    LogLevel,
    MCPConfig,
)


class TestLLMConfig:
    def test_valid_defaults(self) -> None:
        cfg = LLMConfig(provider="anthropic", model="claude-sonnet-4-6")
        assert cfg.max_tokens == 4096
        assert cfg.temperature == 0.0
        assert cfg.max_retries == 3
        assert cfg.timeout_seconds == 120

    def test_max_tokens_positive(self) -> None:
        with pytest.raises(ValueError, match="max_tokens"):
            LLMConfig(provider="x", model="y", max_tokens=0)

    def test_temperature_range(self) -> None:
        with pytest.raises(ValueError, match="temperature"):
            LLMConfig(provider="x", model="y", temperature=-0.1)

        with pytest.raises(ValueError, match="temperature"):
            LLMConfig(provider="x", model="y", temperature=2.1)

    def test_max_retries_non_negative(self) -> None:
        with pytest.raises(ValueError, match="max_retries"):
            LLMConfig(provider="x", model="y", max_retries=-1)

    def test_timeout_positive(self) -> None:
        with pytest.raises(ValueError, match="timeout_seconds"):
            LLMConfig(provider="x", model="y", timeout_seconds=0)

    def test_custom_api_base(self) -> None:
        cfg = LLMConfig(
            provider="deepseek",
            model="deepseek-v4-pro",
            api_base="https://api.deepseek.com/anthropic/v1",
        )
        assert cfg.api_base == "https://api.deepseek.com/anthropic/v1"


class TestDatabaseConfig:
    def test_defaults(self) -> None:
        cfg = DatabaseConfig()
        assert cfg.pool_size == 5
        assert cfg.pool_timeout_seconds == 30
        assert cfg.echo_sql is False
        assert "sqlite" in cfg.url

    def test_pool_size_positive(self) -> None:
        with pytest.raises(ValueError, match="pool_size"):
            DatabaseConfig(pool_size=0)

    def test_pool_timeout_positive(self) -> None:
        with pytest.raises(ValueError, match="pool_timeout_seconds"):
            DatabaseConfig(pool_timeout_seconds=0)


class TestMCPConfig:
    def test_defaults(self) -> None:
        cfg = MCPConfig()
        assert cfg.server_command == "npx"
        assert cfg.timeout_seconds == 30

    def test_timeout_positive(self) -> None:
        with pytest.raises(ValueError, match="timeout_seconds"):
            MCPConfig(timeout_seconds=0)

    def test_with_server_args(self) -> None:
        cfg = MCPConfig(
            server_command="python",
            server_args=("-m", "my_mcp_server"),
            env={"API_KEY": "test"},
        )
        assert cfg.server_args == ("-m", "my_mcp_server")
        assert cfg.env == {"API_KEY": "test"}


class TestAgentConfig:
    def test_defaults(self) -> None:
        cfg = AgentConfig()
        assert cfg.environment == Environment.DEVELOPMENT
        assert cfg.log_level == LogLevel.INFO
        assert cfg.llm.provider == "anthropic"
        assert cfg.max_agent_steps == 50
        assert cfg.human_approval_required is True

    def test_max_agent_steps_positive(self) -> None:
        with pytest.raises(ValueError, match="max_agent_steps"):
            AgentConfig(max_agent_steps=0)

    def test_production_approval_required(self) -> None:
        cfg = AgentConfig(environment=Environment.PRODUCTION)
        assert cfg.human_approval_required is True

    def test_immutable(self) -> None:
        cfg = AgentConfig()
        with pytest.raises(Exception):  # dataclass(frozen=True) raises FrozenInstanceError
            cfg.max_agent_steps = 100  # type: ignore[misc]
