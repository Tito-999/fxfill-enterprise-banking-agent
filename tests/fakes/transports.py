"""Fake HTTP and MCP transports for deterministic tests."""

from __future__ import annotations


class FakeHTTPTransport:
    """Deterministic HTTP transport for testing providers."""

    def __init__(self, responses: list[tuple[int, str]] | None = None) -> None:
        self._responses: list[tuple[int, str]] = responses or []
        self._index = 0
        self.requests: list[dict] = []

    def add_response(self, status: int, body: str) -> None:
        self._responses.append((status, body))

    async def post(
        self, url: str, headers: dict[str, str], body: str, timeout: float
    ) -> tuple[int, str]:
        self.requests.append(
            {"url": url, "headers": dict(headers), "body": body, "timeout": timeout}
        )
        if self._index >= len(self._responses):
            raise RuntimeError(
                f"FakeHTTPTransport exhausted after {len(self._responses)} response(s)"
            )
        status, response_body = self._responses[self._index]
        self._index += 1
        # Redact auth header in stored requests
        if "x-api-key" in self.requests[-1]["headers"]:
            self.requests[-1]["headers"]["x-api-key"] = "[REDACTED]"
        return status, response_body


class FakeMCPTransport:
    """Deterministic MCP transport for testing the MCP client adapter."""

    def __init__(self) -> None:
        self._tools: list = []
        self._results: dict[str, list] = {}
        self._call_count: dict[str, int] = {}
        self.connected = False

    def set_tools(self, tools: list) -> None:
        from fxfill_banking_agent.mcp.models import MCPToolSchema

        self._tools = [
            MCPToolSchema(
                name=t["name"],
                description=t.get("description", ""),
                parameters=t.get("parameters", {}),
            )
            for t in tools
        ]

    def set_result(self, tool_name: str, results: list) -> None:
        from fxfill_banking_agent.mcp.models import MCPToolResult

        self._results[tool_name] = [
            MCPToolResult(
                tool_name=r["tool_name"],
                success=r["success"],
                content=r.get("content", ""),
                error=r.get("error"),
            )
            if isinstance(r, dict)
            else r
            for r in results
        ]
        self._call_count[tool_name] = 0

    async def connect(self) -> None:
        self.connected = True

    async def disconnect(self) -> None:
        self.connected = False

    async def list_tools(self) -> list:
        return list(self._tools)

    async def invoke_tool(self, name: str, arguments: dict) -> dict:
        from fxfill_banking_agent.mcp.models import MCPToolResult

        idx = self._call_count.get(name, 0)
        results = self._results.get(name, [])
        if idx >= len(results):
            return MCPToolResult(tool_name=name, success=False, error="No more responses")
        result = results[idx]
        self._call_count[name] = idx + 1
        return result
