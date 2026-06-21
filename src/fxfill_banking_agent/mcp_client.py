"""MCP client stub for the banking agent.

In Phase 1 this is a stub — it records invocations and returns
programmed responses. Phase 2+ will connect to real MCP servers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ToolCall:
    """A single tool invocation.

    Attributes:
        name: Tool name (e.g. "lookup_account").
        arguments: Keyword arguments for the tool.
    """

    name: str
    arguments: dict[str, object]


@dataclass(frozen=True)
class ToolResult:
    """Result returned by a tool execution.

    Attributes:
        tool_name: The tool that was called.
        success: Whether the call succeeded.
        content: The tool's output (stringified).
        error: Error message if the call failed.
    """

    tool_name: str
    success: bool
    content: str = ""
    error: str | None = None


class MCPClient(Protocol):
    """Protocol for the Model Context Protocol client.

    In production this connects to an MCP server process. In Phase 1
    this is a stub that returns programmed responses.
    """

    async def call_tool(self, call: ToolCall) -> ToolResult:
        """Invoke a tool on the MCP server.

        Args:
            call: The tool name and arguments.

        Returns:
            The tool's result.
        """
        ...


class StubMCPClient:
    """Deterministic stub that returns pre-programmed responses.

    Each registered tool maps to a function that receives the
    arguments and returns the result string.
    """

    def __init__(
        self,
        tools: dict[str, ToolResult | list[ToolResult]] | None = None,
    ) -> None:
        """Create a stub client with pre-registered tool responses.

        Args:
            tools: Mapping of tool_name → result(s). When a list is
                given, results are consumed in order (like a queue).
        """
        self._tools: dict[str, list[ToolResult]] = {}
        self._counters: dict[str, int] = {}
        for name, results in (tools or {}).items():
            if isinstance(results, list):
                self._tools[name] = list(results)
            else:
                self._tools[name] = [results]
            self._counters[name] = 0
        self.calls: list[ToolCall] = []

    def register(self, name: str, results: ToolResult | list[ToolResult]) -> None:
        """Register or replace a tool's programmed response."""
        if isinstance(results, list):
            self._tools[name] = list(results)
        else:
            self._tools[name] = [results]
        self._counters[name] = 0

    async def call_tool(self, call: ToolCall) -> ToolResult:
        """Return the next programmed response for the named tool.

        Raises:
            ValueError: If the tool is not registered.
            RuntimeError: If the tool's response queue is exhausted.
        """
        self.calls.append(call)

        if call.name not in self._tools:
            return ToolResult(
                tool_name=call.name,
                success=False,
                error=f"Unknown tool: {call.name!r}",
            )

        idx = self._counters[call.name]
        if idx >= len(self._tools[call.name]):
            raise RuntimeError(
                f"StubMCPClient exhausted for tool {call.name!r} after {idx} call(s)"
            )

        result = self._tools[call.name][idx]
        self._counters[call.name] += 1
        return result
