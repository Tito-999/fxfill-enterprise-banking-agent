"""Base types for LLM providers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ProviderConfig:
    """Configuration for an LLM provider.

    Attributes:
        provider_type: Provider identifier ("deepseek", "anthropic", etc.).
        base_url: API base URL.
        model: Model name.
        token_env_var: Environment variable name for the API token.
        request_timeout: HTTP request timeout in seconds.
        max_retries: Maximum retry count for transient failures.
        retry_backoff: Initial backoff in seconds (doubles each retry).
        max_tokens: Default max tokens for generation.
        temperature: Default temperature.
    """

    provider_type: str = "deepseek"
    base_url: str = "https://api.deepseek.com/anthropic/v1"
    model: str = "deepseek-v4-pro"
    token_env_var: str = "DEEPSEEK_API_TOKEN"
    request_timeout: float = 120.0
    max_retries: int = 3
    retry_backoff: float = 1.0
    max_tokens: int = 4096
    temperature: float = 0.0


@dataclass
class ProviderResponse:
    """Normalized response from an LLM provider.

    Attributes:
        content: Text content of the response.
        tool_calls: Structured tool calls (if any).
        usage_input_tokens: Input token count.
        usage_output_tokens: Output token count.
        latency_ms: Request latency in milliseconds.
        request_id: Provider-assigned request ID.
        model: Model that produced the response.
    """

    content: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    usage_input_tokens: int = 0
    usage_output_tokens: int = 0
    latency_ms: float = 0.0
    request_id: str = ""
    model: str = ""


class ProviderTransport(Protocol):
    """Injectable HTTP transport for provider requests.

    This protocol allows tests to inject deterministic transports
    without making real network calls.
    """

    async def post(
        self, url: str, headers: dict[str, str], body: str, timeout: float
    ) -> tuple[int, str]:
        """Send a POST request and return (status_code, response_body)."""
        ...
