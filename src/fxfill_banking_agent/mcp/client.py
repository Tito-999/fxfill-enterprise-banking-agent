"""Real MCP client adapter — delegates to an MCP server via transport."""

from __future__ import annotations

from typing import Protocol

from fxfill_banking_agent.logging import get_logger
from fxfill_banking_agent.mcp.models import MCPToolResult, MCPToolSchema
from fxfill_banking_agent.mcp_client import ToolCall, ToolResult

logger = get_logger(__name__)


class MCPTransport(Protocol):
    """Injectable transport for MCP communication."""

    async def connect(self) -> None: ...
    async def list_tools(self) -> list[MCPToolSchema]: ...
    async def invoke_tool(self, name: str, arguments: dict) -> MCPToolResult: ...
    async def disconnect(self) -> None: ...


class MCPClientAdapter:
    """Real MCP client that delegates to a transport.

    Does not make authorization decisions — that is the graph's
    responsibility (ADR 004).
    """

    def __init__(self, transport: MCPTransport, *, timeout: float = 30.0) -> None:
        self._transport = transport
        self._timeout = timeout
        self._connected = False
        self._tools: dict[str, MCPToolSchema] = {}

    async def connect(self) -> None:
        await self._transport.connect()
        self._connected = True
        tools = await self._transport.list_tools()
        self._tools = {t.name: t for t in tools}
        logger.info("mcp_connected", tool_count=len(self._tools))

    async def disconnect(self) -> None:
        await self._transport.disconnect()
        self._connected = False
        self._tools.clear()

    @property
    def tools(self) -> dict[str, MCPToolSchema]:
        return dict(self._tools)

    async def call_tool(self, call: ToolCall) -> ToolResult:
        if not self._connected:
            raise RuntimeError("MCP client not connected")

        try:
            result = await self._transport.invoke_tool(call.name, call.arguments)
            return ToolResult(
                tool_name=call.name,
                success=result.success,
                content=result.content,
                error=result.error,
            )
        except Exception as exc:
            logger.error("mcp_tool_error", tool=call.name, error=str(exc))
            return ToolResult(tool_name=call.name, success=False, error=str(exc))
