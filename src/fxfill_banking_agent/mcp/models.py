"""MCP data models."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MCPToolSchema:
    """Normalized MCP tool schema."""

    name: str
    description: str = ""
    parameters: dict = field(default_factory=dict)


@dataclass
class MCPToolResult:
    """Normalized MCP tool invocation result."""

    tool_name: str
    success: bool
    content: str = ""
    error: str | None = None
    request_id: str = ""
