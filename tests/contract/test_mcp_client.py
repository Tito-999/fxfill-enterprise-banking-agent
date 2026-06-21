"""Contract tests for MCP client adapter."""

from __future__ import annotations

import pytest

from fxfill_banking_agent.mcp.client import MCPClientAdapter
from tests.fakes.transports import FakeMCPTransport


class TestMCPClient:
    @pytest.mark.asyncio
    async def test_connect_and_discover(self) -> None:
        transport = FakeMCPTransport()
        transport.set_tools([{"name": "get_balance", "description": "Get balance"}])
        client = MCPClientAdapter(transport)
        await client.connect()
        assert len(client.tools) == 1
        assert "get_balance" in client.tools
        await client.disconnect()

    @pytest.mark.asyncio
    async def test_tool_invocation(self) -> None:
        transport = FakeMCPTransport()
        transport.set_tools([{"name": "ping", "description": "Ping"}])
        transport.set_result("ping", [{"tool_name": "ping", "success": True, "content": "pong"}])
        client = MCPClientAdapter(transport)
        await client.connect()
        from fxfill_banking_agent.mcp_client import ToolCall

        result = await client.call_tool(ToolCall(name="ping", arguments={}))
        assert result.success
        assert result.content == "pong"
        await client.disconnect()

    @pytest.mark.asyncio
    async def test_not_connected_raises(self) -> None:
        transport = FakeMCPTransport()
        client = MCPClientAdapter(transport)
        from fxfill_banking_agent.mcp_client import ToolCall

        with pytest.raises(RuntimeError, match="not connected"):
            await client.call_tool(ToolCall(name="x", arguments={}))

    @pytest.mark.asyncio
    async def test_unknown_tool(self) -> None:
        transport = FakeMCPTransport()
        transport.set_tools([{"name": "only_this"}])
        transport.set_result(
            "unknown_tool", [{"tool_name": "unknown_tool", "success": False, "error": "not found"}]
        )
        client = MCPClientAdapter(transport)
        await client.connect()
        from fxfill_banking_agent.mcp_client import ToolCall

        result = await client.call_tool(ToolCall(name="unknown_tool", arguments={}))
        assert not result.success
        await client.disconnect()
