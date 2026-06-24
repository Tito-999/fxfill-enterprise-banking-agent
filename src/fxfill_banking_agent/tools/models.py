"""Tool definition models — the single source of truth for tool metadata.

Every tool the agent can call must have a ``ToolDefinition`` that
declares its name, description, schema, side-effect classification,
risk level, required permissions, and execution parameters.

This replaces substring-based tool name guessing (see ADR DECISION-004).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ToolDefinition(BaseModel):
    """Complete metadata for one agent-callable tool.

    Attributes:
        name: Unique tool name (e.g. "get_balance").
        description: Human-readable description sent to the LLM.
        input_schema: JSON Schema for the tool's arguments.
        side_effect: ``True`` if the tool mutates state.
        risk_level: One of ``low``, ``medium``, ``high``, ``critical``.
        required_permissions: Permission strings required to call this tool.
        approval_policy: When human approval is needed:
            ``"never"``, ``"high_risk"``, ``"always"``.
        idempotency_required: ``True`` if idempotency key is mandatory.
        retry_policy: How to handle failures:
            ``"allow"``, ``"never_on_unknown"``, ``"never"``.
        data_classification: Sensitivity of the data this tool accesses.
        timeout_seconds: Max execution time before the tool is considered
            timed out.
        tags: Arbitrary tags for grouping and filtering.
    """

    name: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    input_schema: dict[str, Any] = Field(default_factory=dict)
    side_effect: bool = False
    risk_level: Literal["low", "medium", "high", "critical"] = "low"
    required_permissions: list[str] = Field(default_factory=list)
    approval_policy: Literal["never", "high_risk", "always"] = "never"
    idempotency_required: bool = False
    retry_policy: Literal["allow", "never_on_unknown", "never"] = "allow"
    data_classification: str = "internal"
    timeout_seconds: float = 30.0
    tags: list[str] = Field(default_factory=list)

    @property
    def is_read_only(self) -> bool:
        """True when the tool has no side effects and low risk."""
        return not self.side_effect and self.risk_level == "low"

    @property
    def requires_approval(self) -> bool:
        """True when this tool's policy demands human approval."""
        if self.approval_policy == "never":
            return False
        if self.approval_policy == "always":
            return True
        # "high_risk": only when risk_level is high or critical
        return self.risk_level in ("high", "critical")

    def provider_schema(self, *, include_server_fields: bool = True) -> dict[str, Any]:
        """Return the tool schema in OpenAI function-calling format.

        Args:
            include_server_fields: When False, strip fields that the server
                injects (e.g. ``user_id``). Default True (full schema).
        """
        properties = dict(self.input_schema.get("properties", {}))
        required: list[str] = list(self.input_schema.get("required", []))

        if not include_server_fields:
            # Remove server-injected identity fields from model-visible schema
            server_fields = {"user_id", "tenant_id", "approver_id"}
            properties = {k: v for k, v in properties.items() if k not in server_fields}
            required = [r for r in required if r not in server_fields]

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }
