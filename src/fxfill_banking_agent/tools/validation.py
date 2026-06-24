"""Deterministic tool-call validation.

Every LLM-produced tool call must pass through this module before
execution. Validation is deterministic — it never calls an LLM.

Pipeline:
    1. Tool name allowlist check (must exist in registry)
    2. JSON type coercion (string → dict/list/number)
    3. JSON Schema / Pydantic validation
    4. Trusted-context field injection (done by caller, not here)
    → authorization
    → idempotency reservation
    → execution
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fxfill_banking_agent.tools.registry import ToolRegistry


@dataclass(frozen=True)
class ToolCallValidation:
    """Result of validating an LLM-produced tool call.

    Attributes:
        valid: ``True`` when the call passes all checks.
        tool_name: The validated (or rejected) tool name.
        validated_args: The validated and coerced arguments (empty if invalid).
        error: Human-readable error when ``valid`` is False.
        error_code: Machine-readable error code.
    """

    valid: bool
    tool_name: str
    validated_args: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    error_code: str = ""


def validate_tool_call(
    tool_name: str,
    arguments: Any,
    registry: ToolRegistry,
) -> ToolCallValidation:
    """Validate an LLM-produced tool call against the registry.

    Args:
        tool_name: The tool name proposed by the model.
        arguments: Raw arguments from the model (may be dict or str).
        registry: The tool registry to validate against.

    Returns:
        A ``ToolCallValidation`` with the result.
    """
    # ── Step 1: Name allowlist ──────────────────────────────────────
    definition = registry.get(tool_name)
    if definition is None:
        return ToolCallValidation(
            valid=False,
            tool_name=tool_name,
            error=f"Unknown tool: {tool_name!r}",
            error_code="UNKNOWN_TOOL",
        )

    # ── Step 2: Normalize arguments to dict ─────────────────────────
    if arguments is None:
        args: dict[str, Any] = {}
    elif isinstance(arguments, str):
        import json

        try:
            parsed = json.loads(arguments)
        except json.JSONDecodeError:
            return ToolCallValidation(
                valid=False,
                tool_name=tool_name,
                error=f"Tool arguments must be valid JSON for {tool_name!r}",
                error_code="INVALID_JSON_ARGS",
            )
        if not isinstance(parsed, dict):
            return ToolCallValidation(
                valid=False,
                tool_name=tool_name,
                error=f"Tool arguments must be a JSON object for {tool_name!r}",
                error_code="ARGS_NOT_OBJECT",
            )
        args = parsed
    elif isinstance(arguments, dict):
        args = arguments
    else:
        return ToolCallValidation(
            valid=False,
            tool_name=tool_name,
            error=f"Tool arguments must be a dict for {tool_name!r}, got {type(arguments).__name__}",
            error_code="ARGS_NOT_DICT",
        )

    # ── Step 3: Schema validation ───────────────────────────────────
    schema = definition.input_schema
    if not schema:
        # No schema defined — accept any arguments (for extensibility)
        return ToolCallValidation(valid=True, tool_name=tool_name, validated_args=args)

    result = _validate_against_schema(tool_name, args, schema)
    if result is not None:
        return result

    return ToolCallValidation(valid=True, tool_name=tool_name, validated_args=args)


def _validate_against_schema(
    tool_name: str,
    args: dict[str, Any],
    schema: dict[str, Any],
) -> ToolCallValidation | None:
    """Validate args against a JSON Schema. Returns None on success."""
    required: list[str] = schema.get("required", [])
    properties: dict[str, dict[str, Any]] = schema.get("properties", {})

    # Check required fields
    for req_field in required:
        if req_field not in args or args[req_field] is None:
            return ToolCallValidation(
                valid=False,
                tool_name=tool_name,
                error=f"Missing required parameter: {req_field!r} for tool {tool_name!r}",
                error_code="MISSING_REQUIRED_PARAMETER",
            )

    # Type-check each provided field
    for field_name, value in args.items():
        prop = properties.get(field_name)
        if prop is None:
            # Unknown field — allow through (forward compatibility)
            continue

        expected_type = prop.get("type", "string")
        if not _check_type(value, expected_type):
            return ToolCallValidation(
                valid=False,
                tool_name=tool_name,
                error=(
                    f"Type mismatch for {field_name!r} in {tool_name!r}: "
                    f"expected {expected_type}, got {type(value).__name__}"
                ),
                error_code="TYPE_MISMATCH",
            )

    return None  # OK


def _check_type(value: Any, expected: str) -> bool:
    """Check if *value* matches the JSON Schema *expected* type."""
    if expected == "string":
        return isinstance(value, str)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    return True  # unknown type — accept
