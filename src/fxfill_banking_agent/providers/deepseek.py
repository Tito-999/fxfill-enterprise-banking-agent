"""DeepSeek LLM provider via Anthropic-compatible API.

Never stores tokens in source code or configuration files.
Tokens are read from environment variables at construction time only.
"""

from __future__ import annotations

import json
import random
import time as time_mod
import uuid
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage

from fxfill_banking_agent.logging import get_logger
from fxfill_banking_agent.providers.base import ProviderConfig, ProviderResponse, ProviderTransport

logger = get_logger(__name__)

# HTTP status codes that warrant a retry
RETRYABLE_STATUSES: frozenset[int] = frozenset({408, 429, 500, 502, 503})
NON_RETRYABLE_STATUSES: frozenset[int] = frozenset({400, 401, 403, 409})


class DeepSeekProvider:
    """DeepSeek LLM provider using the Anthropic-compatible Messages API.

    Args:
        config: Provider configuration.
        token: API token (read from environment; never logged).
        transport: Injectable HTTP transport for testing.
    """

    def __init__(
        self,
        config: ProviderConfig,
        token: str,
        transport: ProviderTransport | None = None,
    ) -> None:
        self._config = config
        self._token = token
        self._transport = transport or _RealHTTPTransport()
        self._closed = False

    async def invoke(
        self,
        messages: list[BaseMessage],
        *,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> AIMessage:
        """Send messages to DeepSeek and return the AI response.

        Converts LangChain messages to the provider format, sends the
        request with retry/backoff, and parses the response back into
        an AIMessage.

        Args:
            messages: The conversation history.
            tools: Optional tool schemas in OpenAI function-calling format.
            tool_choice: Optional tool selection control
                (``"auto"``, ``"none"``, ``"required"``, or a specific tool dict).
        """
        if self._closed:
            raise RuntimeError("DeepSeekProvider is closed")

        correlation_id = str(uuid.uuid4())
        body = self._build_request_body(messages, tools=tools, tool_choice=tool_choice)
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._token}",
            "X-Correlation-Id": correlation_id,
        }

        t0 = time_mod.monotonic()
        status, raw = await self._request_with_retry(
            self._config.base_url + "/chat/completions",
            headers,
            json.dumps(body),
        )
        latency_ms = (time_mod.monotonic() - t0) * 1000

        parsed = self._parse_response(status, raw, latency_ms, correlation_id)
        logger.info(
            "provider_response",
            model=parsed.model,
            latency_ms=round(parsed.latency_ms, 1),
            input_tokens=parsed.usage_input_tokens,
            output_tokens=parsed.usage_output_tokens,
            request_id=parsed.request_id,
            correlation_id=correlation_id,
        )

        return self._to_ai_message(parsed)

    async def close(self) -> None:
        """Clean shutdown of the provider."""
        self._closed = True
        if hasattr(self._transport, "close"):
            await self._transport.close()  # type: ignore[attr-defined]

    def _build_request_body(
        self,
        messages: list[BaseMessage],
        *,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        converted: list[dict[str, Any]] = []
        for m in messages:
            role = _map_role(type(m).__name__)
            content: Any = m.content if hasattr(m, "content") else str(m)

            msg: dict[str, Any] = {"role": role, "content": content}
            if hasattr(m, "tool_calls") and m.tool_calls:  # type: ignore[union-attr]
                msg["tool_calls"] = m.tool_calls  # type: ignore[union-attr]
            if hasattr(m, "tool_call_id") and m.tool_call_id:  # type: ignore[union-attr]
                msg["tool_call_id"] = m.tool_call_id  # type: ignore[union-attr]

            converted.append(msg)

        body: dict[str, Any] = {
            "model": self._config.model,
            "max_tokens": self._config.max_tokens,
            "temperature": self._config.temperature,
            "messages": converted,
        }

        if tools:
            body["tools"] = tools
        if tool_choice is not None:
            body["tool_choice"] = tool_choice

        return body

    async def _request_with_retry(
        self, url: str, headers: dict[str, str], body: str
    ) -> tuple[int, str]:
        last_exc: Exception | None = None
        backoff = self._config.retry_backoff

        for attempt in range(self._config.max_retries + 1):
            try:
                status, response_body = await self._transport.post(
                    url, headers, body, self._config.request_timeout
                )
                if status in NON_RETRYABLE_STATUSES:
                    return status, response_body
                if status in RETRYABLE_STATUSES and attempt < self._config.max_retries:
                    logger.warning("provider_retry", status=status, attempt=attempt + 1)
                    await _async_sleep(backoff + random.uniform(0, backoff * 0.5))
                    backoff *= 2
                    continue
                return status, response_body
            except Exception as exc:
                last_exc = exc
                if attempt < self._config.max_retries:
                    logger.warning("provider_retry_exception", error=str(exc), attempt=attempt + 1)
                    await _async_sleep(backoff + random.uniform(0, backoff * 0.5))
                    backoff *= 2
                else:
                    raise RuntimeError(
                        f"Provider request failed after {self._config.max_retries + 1} attempts: {exc}"
                    ) from exc

        raise RuntimeError(f"Provider request failed: {last_exc}")

    def _parse_response(
        self, status: int, raw: str, latency_ms: float, correlation_id: str
    ) -> ProviderResponse:
        if status == 401:
            raise RuntimeError("Provider authentication failed — check your API token")
        if status == 403:
            raise RuntimeError("Provider authorization failed — check your account permissions")
        if status == 400:
            raise RuntimeError(f"Provider rejected request (400): {raw[:500]}")
        if status == 429:
            raise RuntimeError("Provider rate limit exceeded — retry exhausted")
        if status >= 500:
            raise RuntimeError(f"Provider server error ({status}): {raw[:500]}")

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            raise RuntimeError(f"Provider returned malformed JSON (status {status}): {raw[:500]}")

        content = ""
        tool_calls: list[dict[str, Any]] = []
        choice = (data.get("choices") or [{}])[0] if "choices" in data else data
        msg = choice.get("message", {})

        # Debug: log raw response for diagnosis
        if not msg.get("content"):
            logger.info(
                "provider_debug_raw",
                raw_first_500=raw[:500],
                choice=choice,
                msg_keys=list(msg.keys()) if isinstance(msg, dict) else "not_dict",
            )

        if isinstance(msg, dict):
            content = msg.get("content", "") or ""
            # DeepSeek may return content directly at top level
            if not content and "content" in data:
                content = data.get("content", "") or ""
            raw_tool_calls = msg.get("tool_calls", [])
            if raw_tool_calls:
                tool_calls = [
                    {
                        "name": tc["function"]["name"],
                        "args": json.loads(tc["function"]["arguments"]),
                        "id": tc["id"],
                    }
                    if isinstance(tc.get("function", {}).get("arguments"), str)
                    else {
                        "name": tc["function"]["name"],
                        "args": tc["function"]["arguments"],
                        "id": tc["id"],
                    }
                    for tc in raw_tool_calls
                ]

        usage = data.get("usage", {})
        return ProviderResponse(
            content=content,
            tool_calls=tool_calls,
            usage_input_tokens=usage.get("prompt_tokens", 0),
            usage_output_tokens=usage.get("completion_tokens", 0),
            latency_ms=latency_ms,
            request_id=data.get("id", ""),
            model=data.get("model", self._config.model),
        )

    @staticmethod
    def _to_ai_message(response: ProviderResponse) -> AIMessage:
        if response.tool_calls:
            return AIMessage(content=response.content or "", tool_calls=response.tool_calls)
        return AIMessage(content=response.content)


# ── Helpers ───────────────────────────────────────────────────────────


def _map_role(lc_type: str) -> str:
    mapping = {
        "HumanMessage": "user",
        "AIMessage": "assistant",
        "SystemMessage": "system",
        "ToolMessage": "tool",
    }
    return mapping.get(lc_type, "user")


async def _async_sleep(seconds: float) -> None:
    import asyncio

    await asyncio.sleep(seconds)


class _RealHTTPTransport:
    """Production HTTP transport using httpx."""

    async def post(
        self, url: str, headers: dict[str, str], body: str, timeout: float
    ) -> tuple[int, str]:
        import httpx

        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout)) as client:
            resp = await client.post(url, headers=headers, content=body)
            return resp.status_code, resp.text

    async def close(self) -> None:
        pass
