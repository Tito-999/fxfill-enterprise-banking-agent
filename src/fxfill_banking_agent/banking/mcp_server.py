"""Synthetic banking MCP server — in-process adapter for tests and dev."""

from __future__ import annotations

from fxfill_banking_agent.banking.fixtures import create_test_repository
from fxfill_banking_agent.banking.repository import BankingRepository
from fxfill_banking_agent.banking.tools import BankingTools
from fxfill_banking_agent.mcp.models import MCPToolResult, MCPToolSchema


class BankingMCPServer:
    """In-process synthetic MCP server backed by BankingRepository.

    This is a local adapter — not a real subprocess MCP server.
    It implements the MCPTransport protocol for direct integration.
    """

    def __init__(self, repo: BankingRepository | None = None) -> None:
        self._repo = repo or create_test_repository()
        self._tools = BankingTools(self._repo)

    async def connect(self) -> None:
        pass

    async def list_tools(self) -> list[MCPToolSchema]:
        schemas = self._tools.tool_schemas()
        return [
            MCPToolSchema(
                name=s["name"],
                description=s.get("description", ""),
                parameters=s.get("parameters", {}),
            )
            for s in schemas
        ]

    async def invoke_tool(self, name: str, arguments: dict) -> MCPToolResult:
        result, error = self._tools.execute(name, arguments)
        if error:
            return MCPToolResult(tool_name=name, success=False, error=error)
        return MCPToolResult(tool_name=name, success=True, content=result)

    async def disconnect(self) -> None:
        pass

    @property
    def repository(self) -> BankingRepository:
        return self._repo
