"""Contract tests for DeepSeekProvider with fake HTTP transport."""

from __future__ import annotations

import json

import pytest

from fxfill_banking_agent.providers.base import ProviderConfig
from fxfill_banking_agent.providers.deepseek import DeepSeekProvider
from tests.fakes.transports import FakeHTTPTransport


def _make_response(
    content: str = "Hello!",
    tool_calls=None,
    model="deepseek-v4-pro",
    request_id="req-1",
    usage_input=10,
    usage_output=5,
) -> str:
    body = {
        "id": request_id,
        "model": model,
        "choices": [{"message": {"content": content, "role": "assistant"}}],
        "usage": {"prompt_tokens": usage_input, "completion_tokens": usage_output},
    }
    if tool_calls:
        body["choices"][0]["message"]["tool_calls"] = tool_calls
    return json.dumps(body)


class TestDeepSeekProvider:
    def test_valid_text_response(self) -> None:
        transport = FakeHTTPTransport([(200, _make_response("Your balance is $100."))])
        provider = DeepSeekProvider(ProviderConfig(), "test-token", transport=transport)
        import asyncio

        from langchain_core.messages import HumanMessage

        msg = asyncio.get_event_loop().run_until_complete(
            provider.invoke([HumanMessage(content="balance?")])
        )
        assert msg.content == "Your balance is $100."
        assert "test-token" not in str(transport.requests)

    def test_tool_call_response(self) -> None:
        tc = [
            {
                "id": "t1",
                "type": "function",
                "function": {"name": "get_balance", "arguments": '{"account": "A1"}'},
            }
        ]
        transport = FakeHTTPTransport([(200, _make_response("", tool_calls=tc))])
        provider = DeepSeekProvider(ProviderConfig(), "test-token", transport=transport)
        import asyncio

        from langchain_core.messages import HumanMessage

        msg = asyncio.get_event_loop().run_until_complete(
            provider.invoke([HumanMessage(content="balance")])
        )
        assert len(msg.tool_calls) == 1
        assert msg.tool_calls[0]["name"] == "get_balance"
        assert msg.tool_calls[0]["args"] == {"account": "A1"}
        assert msg.tool_calls[0]["id"] == "t1"

    def test_auth_failure_raises(self) -> None:
        transport = FakeHTTPTransport([(401, '{"error":"unauthorized"}')])
        provider = DeepSeekProvider(ProviderConfig(), "bad-token", transport=transport)
        import asyncio

        from langchain_core.messages import HumanMessage

        with pytest.raises(RuntimeError, match="authentication"):
            asyncio.get_event_loop().run_until_complete(
                provider.invoke([HumanMessage(content="hi")])
            )

    def test_rate_limit_raises(self) -> None:
        transport = FakeHTTPTransport([(429, '{"error":"rate limited"}')])
        provider = DeepSeekProvider(ProviderConfig(max_retries=0), "token", transport=transport)
        import asyncio

        from langchain_core.messages import HumanMessage

        with pytest.raises(RuntimeError, match="rate limit"):
            asyncio.get_event_loop().run_until_complete(
                provider.invoke([HumanMessage(content="hi")])
            )

    def test_malformed_json_raises(self) -> None:
        transport = FakeHTTPTransport([(200, "not json")])
        provider = DeepSeekProvider(ProviderConfig(), "token", transport=transport)
        import asyncio

        from langchain_core.messages import HumanMessage

        with pytest.raises(RuntimeError, match="malformed"):
            asyncio.get_event_loop().run_until_complete(
                provider.invoke([HumanMessage(content="hi")])
            )

    def test_retry_on_transient(self) -> None:
        transport = FakeHTTPTransport([(503, "unavailable"), (200, _make_response("Recovered"))])
        provider = DeepSeekProvider(
            ProviderConfig(max_retries=1, retry_backoff=0.01), "token", transport=transport
        )
        import asyncio

        from langchain_core.messages import HumanMessage

        msg = asyncio.get_event_loop().run_until_complete(
            provider.invoke([HumanMessage(content="hi")])
        )
        assert msg.content == "Recovered"
        assert len(transport.requests) == 2

    def test_credential_redaction(self) -> None:
        transport = FakeHTTPTransport([(200, _make_response("ok"))])
        provider = DeepSeekProvider(ProviderConfig(), "secret-token-12345", transport=transport)
        import asyncio

        from langchain_core.messages import HumanMessage

        asyncio.get_event_loop().run_until_complete(provider.invoke([HumanMessage(content="hi")]))
        for req in transport.requests:
            assert "secret-token-12345" not in str(req)
            assert (
                req["headers"].get("x-api-key") == "[REDACTED]"
                or req["headers"].get("Authorization") == "[REDACTED]"
            )

    def test_usage_parsing(self) -> None:
        transport = FakeHTTPTransport(
            [(200, _make_response("ok", usage_input=100, usage_output=50))]
        )
        provider = DeepSeekProvider(ProviderConfig(), "token", transport=transport)
        # Usage is logged but not directly exposed on AIMessage — verify it doesn't crash
        import asyncio

        from langchain_core.messages import HumanMessage

        msg = asyncio.get_event_loop().run_until_complete(
            provider.invoke([HumanMessage(content="hi")])
        )
        assert msg.content == "ok"

    def test_shutdown(self) -> None:
        transport = FakeHTTPTransport([(200, _make_response("ok"))])
        provider = DeepSeekProvider(ProviderConfig(), "token", transport=transport)
        import asyncio

        asyncio.get_event_loop().run_until_complete(provider.close())
        with pytest.raises(RuntimeError, match="closed"):
            from langchain_core.messages import HumanMessage

            asyncio.get_event_loop().run_until_complete(
                provider.invoke([HumanMessage(content="hi")])
            )
