"""MCP client factory."""

from __future__ import annotations

from fxfill_banking_agent.mcp.client import MCPClientAdapter, MCPTransport
from fxfill_banking_agent.mcp_client import MCPClient


def create_mcp_client(transport: MCPTransport, *, timeout: float = 30.0) -> MCPClient:
    """Create an MCP client from a transport.

    Production code must provide a real transport. Tests may inject
    a stub transport.
    """
    return MCPClientAdapter(transport, timeout=timeout)
