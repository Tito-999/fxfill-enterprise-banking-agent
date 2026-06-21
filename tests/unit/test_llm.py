"""Tests for LLM abstractions."""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from fxfill_banking_agent.llm import EchoLLM, MockLLM


class TestMockLLM:
    @pytest.mark.asyncio
    async def test_returns_sequence(self) -> None:
        responses = [
            AIMessage(content="first"),
            AIMessage(content="second"),
        ]
        llm = MockLLM(responses)

        msg1 = await llm.invoke([HumanMessage(content="hi")])
        assert msg1.content == "first"
        assert llm.call_count == 1

        msg2 = await llm.invoke([HumanMessage(content="again")])
        assert msg2.content == "second"
        assert llm.call_count == 2

    @pytest.mark.asyncio
    async def test_exhausted_raises(self) -> None:
        llm = MockLLM([AIMessage(content="only")])
        await llm.invoke([HumanMessage(content="hi")])

        with pytest.raises(RuntimeError, match="exhausted"):
            await llm.invoke([HumanMessage(content="too many")])

    @pytest.mark.asyncio
    async def test_defaults_to_done(self) -> None:
        llm = MockLLM()
        msg = await llm.invoke([HumanMessage(content="hi")])
        assert msg.content == "No further actions needed."

    @pytest.mark.asyncio
    async def test_exhausted_property(self) -> None:
        llm = MockLLM([AIMessage(content="one")])
        assert not llm.exhausted
        await llm.invoke([HumanMessage(content="hi")])
        assert llm.exhausted


class TestEchoLLM:
    @pytest.mark.asyncio
    async def test_echoes_last_message(self) -> None:
        llm = EchoLLM()
        msg = await llm.invoke([HumanMessage(content="Hello, world!")])
        assert msg.content == "Echo: Hello, world!"
        assert llm.call_count == 1

    @pytest.mark.asyncio
    async def test_custom_prefix(self) -> None:
        llm = EchoLLM(prefix="Bot: ")
        msg = await llm.invoke([HumanMessage(content="test")])
        assert msg.content == "Bot: test"
