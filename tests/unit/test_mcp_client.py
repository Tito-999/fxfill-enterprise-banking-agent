"""Tests for MCP client stub."""

from __future__ import annotations

import pytest

from fxfill_banking_agent.mcp_client import StubMCPClient, ToolCall, ToolResult


class TestStubMCPClient:
    @pytest.mark.asyncio
    async def test_returns_registered_result(self) -> None:
        client = StubMCPClient(
            tools={"lookup_account": ToolResult("lookup_account", True, "Account #1234")}
        )
        result = await client.call_tool(
            ToolCall(name="lookup_account", arguments={"account_id": "1234"})
        )
        assert result.success is True
        assert result.content == "Account #1234"

    @pytest.mark.asyncio
    async def test_unknown_tool(self) -> None:
        client = StubMCPClient()
        result = await client.call_tool(ToolCall(name="nonexistent", arguments={}))
        assert result.success is False
        assert "Unknown tool" in (result.error or "")

    @pytest.mark.asyncio
    async def test_queued_responses(self) -> None:
        client = StubMCPClient(
            tools={
                "search": [
                    ToolResult("search", True, "result-1"),
                    ToolResult("search", True, "result-2"),
                ]
            }
        )
        r1 = await client.call_tool(ToolCall("search", {"q": "a"}))
        r2 = await client.call_tool(ToolCall("search", {"q": "b"}))
        assert r1.content == "result-1"
        assert r2.content == "result-2"

    @pytest.mark.asyncio
    async def test_exhausted_queue_raises(self) -> None:
        client = StubMCPClient(tools={"single": ToolResult("single", True, "done")})
        await client.call_tool(ToolCall("single", {}))
        with pytest.raises(RuntimeError, match="exhausted"):
            await client.call_tool(ToolCall("single", {}))

    @pytest.mark.asyncio
    async def test_tracks_calls(self) -> None:
        client = StubMCPClient(
            tools={"a": [ToolResult("a", True, "ok"), ToolResult("a", True, "ok2")]}
        )
        await client.call_tool(ToolCall("a", {"x": 1}))
        await client.call_tool(ToolCall("a", {"x": 2}))

        with pytest.raises(RuntimeError):
            await client.call_tool(ToolCall("a", {"x": 3}))

        assert len(client.calls) == 3
        assert client.calls[0].arguments == {"x": 1}
        assert client.calls[1].arguments == {"x": 2}

    @pytest.mark.asyncio
    async def test_register_adds_tool(self) -> None:
        client = StubMCPClient()
        client.register("new_tool", ToolResult("new_tool", True, "registered"))
        result = await client.call_tool(ToolCall("new_tool", {}))
        assert result.content == "registered"

    @pytest.mark.asyncio
    async def test_register_replaces(self) -> None:
        client = StubMCPClient(tools={"t": ToolResult("t", True, "old")})
        client.register("t", ToolResult("t", True, "new"))
        result = await client.call_tool(ToolCall("t", {}))
        assert result.content == "new"
