"""Typed configuration models for the banking agent runtime.

All configuration values must be validated before use.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class LogLevel(str, Enum):
    """Allowed log levels for the agent runtime."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class Environment(str, Enum):
    """Deployment environments."""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


@dataclass(frozen=True)
class LLMConfig:
    """Configuration for a language model connection.

    Attributes:
        provider: Model provider (e.g. "anthropic", "openai", "deepseek").
        model: Model identifier string.
        api_base: Optional custom API base URL.
        max_tokens: Default max tokens for generation.
        temperature: Sampling temperature (0.0–2.0).
        max_retries: Maximum retry count for transient failures.
        timeout_seconds: Request timeout in seconds.
    """

    provider: str
    model: str
    api_base: Optional[str] = None
    max_tokens: int = 4096
    temperature: float = 0.0
    max_retries: int = 3
    timeout_seconds: int = 120

    def __post_init__(self) -> None:
        if self.max_tokens < 1:
            raise ValueError("max_tokens must be >= 1")
        if not (0.0 <= self.temperature <= 2.0):
            raise ValueError("temperature must be in [0.0, 2.0]")
        if self.max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        if self.timeout_seconds < 1:
            raise ValueError("timeout_seconds must be >= 1")


@dataclass(frozen=True)
class DatabaseConfig:
    """Configuration for database connections.

    Attributes:
        url: Database connection URL (e.g. postgresql+asyncpg://...).
        pool_size: Connection pool size.
        pool_timeout_seconds: Max wait time for a connection from the pool.
        echo_sql: When True, log all SQL statements (development only).
    """

    url: str = "sqlite+aiosqlite:///./data/agent.db"
    pool_size: int = 5
    pool_timeout_seconds: int = 30
    echo_sql: bool = False

    def __post_init__(self) -> None:
        if self.pool_size < 1:
            raise ValueError("pool_size must be >= 1")
        if self.pool_timeout_seconds < 1:
            raise ValueError("pool_timeout_seconds must be >= 1")


@dataclass(frozen=True)
class MCPConfig:
    """Configuration for Model Context Protocol servers.

    Attributes:
        server_command: The command to launch the MCP server.
        server_args: Arguments passed to the server command.
        env: Environment variables for the server process.
        timeout_seconds: Startup timeout for the server.
    """

    server_command: str = "npx"
    server_args: tuple[str, ...] = ()
    env: dict[str, str] = field(default_factory=dict)
    timeout_seconds: int = 30

    def __post_init__(self) -> None:
        if self.timeout_seconds < 1:
            raise ValueError("timeout_seconds must be >= 1")


@dataclass(frozen=True)
class AgentConfig:
    """Top-level configuration for the banking agent.

    Attributes:
        environment: Deployment environment.
        log_level: Minimum log level.
        llm: LLM configuration.
        database: Database configuration.
        mcp: MCP server configuration.
        max_agent_steps: Hard limit on agent reasoning + tool-call loops.
        human_approval_required: When True, side-effecting operations
            require explicit human approval.
    """

    environment: Environment = Environment.DEVELOPMENT
    log_level: LogLevel = LogLevel.INFO
    llm: LLMConfig = field(
        default_factory=lambda: LLMConfig(provider="anthropic", model="claude-sonnet-4-6")
    )
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    mcp: MCPConfig = field(default_factory=MCPConfig)
    max_agent_steps: int = 50
    human_approval_required: bool = True

    def __post_init__(self) -> None:
        if self.max_agent_steps < 1:
            raise ValueError("max_agent_steps must be >= 1")
