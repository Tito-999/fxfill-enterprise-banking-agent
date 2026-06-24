"""Provider-specific tool schema adapters.

Each adapter converts ``ToolDefinition`` objects to the format
expected by a specific LLM provider's API.

Currently supported:
- OpenAI-compatible (DeepSeek, OpenAI, etc.)
- Anthropic-compatible (Claude, etc.)
"""

from __future__ import annotations

from typing import Any

from fxfill_banking_agent.tools.models import ToolDefinition


def to_openai_tools(
    tools: list[ToolDefinition],
    *,
    include_server_fields: bool = False,
) -> list[dict[str, Any]]:
    """Convert tool definitions to OpenAI function-calling format.

    Example output::

        [{
            "type": "function",
            "function": {
                "name": "get_balance",
                "description": "Get account balance",
                "parameters": {
                    "type": "object",
                    "properties": {...},
                    "required": [...]
                }
            }
        }]
    """
    return [t.provider_schema(include_server_fields=include_server_fields) for t in tools]


def to_anthropic_tools(
    tools: list[ToolDefinition],
    *,
    include_server_fields: bool = False,
) -> list[dict[str, Any]]:
    """Convert tool definitions to Anthropic tool format.

    Example output::

        [{
            "name": "get_balance",
            "description": "Get account balance",
            "input_schema": {
                "type": "object",
                "properties": {...},
                "required": [...]
            }
        }]
    """
    result: list[dict[str, Any]] = []
    for t in tools:
        properties = dict(t.input_schema.get("properties", {}))
        required: list[str] = list(t.input_schema.get("required", []))

        if not include_server_fields:
            server_fields = {"user_id", "tenant_id", "approver_id"}
            properties = {k: v for k, v in properties.items() if k not in server_fields}
            required = [r for r in required if r not in server_fields]

        result.append(
            {
                "name": t.name,
                "description": t.description,
                "input_schema": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            }
        )
    return result
