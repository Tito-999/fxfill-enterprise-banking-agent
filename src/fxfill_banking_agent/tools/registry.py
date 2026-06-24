"""Tool registry — the single source of truth for tool metadata and lookups.

The registry owns all ``ToolDefinition`` objects and provides:
- By-name lookup
- Provider schema generation (for LLM function-calling)
- Risk/permission queries for authorization
"""

from __future__ import annotations

from typing import Iterator

from fxfill_banking_agent.tools.models import ToolDefinition


class ToolRegistry:
    """Immutable registry of agent-callable tools.

    Tools are registered at construction time. The registry provides
    lookup, iteration, and provider-schema generation.
    """

    def __init__(self, tools: list[ToolDefinition] | None = None) -> None:
        """Create a registry from a list of tool definitions.

        Args:
            tools: Tool definitions. Duplicate names raise ``ValueError``.
        """
        self._tools: dict[str, ToolDefinition] = {}
        for t in tools or []:
            if t.name in self._tools:
                raise ValueError(f"Duplicate tool name: {t.name!r}")
            self._tools[t.name] = t

    def register(self, tool: ToolDefinition) -> None:
        """Register a new tool after construction.

        Raises:
            ValueError: If the tool name already exists.
        """
        if tool.name in self._tools:
            raise ValueError(f"Duplicate tool name: {tool.name!r}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolDefinition | None:
        """Return the tool definition for *name*, or ``None``."""
        return self._tools.get(name)

    def has(self, name: str) -> bool:
        """True when a tool named *name* is registered."""
        return name in self._tools

    @property
    def names(self) -> frozenset[str]:
        """Set of all registered tool names."""
        return frozenset(self._tools.keys())

    @property
    def count(self) -> int:
        """Number of registered tools."""
        return len(self._tools)

    def __iter__(self) -> Iterator[ToolDefinition]:
        return iter(self._tools.values())

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def provider_definitions(
        self, *, include_server_fields: bool = False
    ) -> list[dict[str, object]]:
        """Return all tool schemas in OpenAI function-calling format.

        Args:
            include_server_fields: When False, server-injected identity
                fields (``user_id``, etc.) are stripped from the schema
                visible to the model.
        """
        return [
            t.provider_schema(include_server_fields=include_server_fields)
            for t in self._tools.values()
        ]

    def side_effecting_tools(self) -> list[ToolDefinition]:
        """Return all tools that have side effects."""
        return [t for t in self._tools.values() if t.side_effect]

    def tools_by_risk(self, minimum_risk: str) -> list[ToolDefinition]:
        """Return tools at or above *minimum_risk* level."""
        levels = {"low": 0, "medium": 1, "high": 2, "critical": 3}
        threshold = levels.get(minimum_risk, 0)
        return [t for t in self._tools.values() if levels.get(t.risk_level, 0) >= threshold]
