"""Observability — OpenTelemetry-compatible tracing, metrics, and evaluation.

P1-08: Provides the instrumentation foundation for:
- Distributed tracing (HTTP → agent → LLM → tool → response)
- Per-component latency and token metrics
- Evaluation dataset management and regression testing
- CI quality gates

Redaction: Traces and logs must never contain API tokens, full account
numbers, PII, or raw banking responses.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SpanKind(str, Enum):
    """Standard span kinds for agent telemetry."""

    HTTP_REQUEST = "http_request"
    AGENT_RUN = "agent_run"
    PROMPT_BUILD = "prompt_build"
    LLM_CALL = "llm_call"
    RETRIEVAL = "retrieval"
    AUTHORIZATION = "authorization"
    TOOL_CALL = "tool_call"
    APPROVAL_WAIT = "approval_wait"
    HITL_RESUME = "hitl_resume"
    FINAL_RESPONSE = "final_response"


@dataclass
class Span:
    """A single span in a trace.

    Attributes:
        span_id: Unique span identifier.
        parent_span_id: Parent span (empty for root).
        trace_id: Trace identifier (correlation_id).
        kind: The kind of operation.
        start_time: ISO-8601 start timestamp.
        end_time: ISO-8601 end timestamp.
        attributes: Key-value metadata (MUST be redacted before export).
        status: "ok" or "error".
    """

    span_id: str
    parent_span_id: str = ""
    trace_id: str = ""
    kind: SpanKind = SpanKind.AGENT_RUN
    start_time: str = ""
    end_time: str = ""
    attributes: dict[str, Any] = field(default_factory=dict)
    status: str = "ok"

    @property
    def duration_ms(self) -> float:
        """Approximate duration in milliseconds."""
        try:
            from datetime import datetime

            if self.start_time and self.end_time:
                t0 = datetime.fromisoformat(self.start_time)
                t1 = datetime.fromisoformat(self.end_time)
                return (t1 - t0).total_seconds() * 1000
        except (ValueError, TypeError):
            pass
        return 0.0


@dataclass
class EvalCase:
    """A single evaluation test case.

    Attributes:
        case_id: Unique case identifier.
        category: e.g. "core_task", "safety", "multiturn".
        description: What this case tests.
        user_message: The input message.
        expected_tool: The expected tool to be called (if known).
        expected_intent: The expected intent classification.
        must_not_call: Tools that must NOT be called.
        min_steps: Minimum expected steps.
        max_steps: Maximum expected steps.
    """

    case_id: str
    category: str = "core_task"
    description: str = ""
    user_message: str = ""
    expected_tool: str = ""
    expected_intent: str = ""
    must_not_call: list[str] = field(default_factory=list)
    min_steps: int = 1
    max_steps: int = 50


@dataclass
class EvalResult:
    """Result of running a single evaluation case.

    Attributes:
        case_id: Which case was run.
        passed: Whether the case passed.
        actual_tool: The tool that was actually called.
        actual_intent: The classified intent.
        step_count: Number of steps taken.
        duration_ms: Total duration.
        error: Error message if failed.
    """

    case_id: str
    passed: bool
    actual_tool: str = ""
    actual_intent: str = ""
    step_count: int = 0
    duration_ms: float = 0.0
    error: str = ""


# ── Redaction ─────────────────────────────────────────────────────────

# Fields to redact from spans/logs before export
_REDACT_FIELDS: frozenset[str] = frozenset(
    {
        "api_key",
        "token",
        "authorization",
        "x-api-key",
        "password",
        "secret",
        "account_number",
        "full_account",
        "ssn",
        "credit_card",
    }
)


def redact_attributes(attrs: dict[str, Any]) -> dict[str, Any]:
    """Remove sensitive fields from span attributes.

    Returns a shallow copy with redacted fields replaced by "[REDACTED]".
    """
    result: dict[str, Any] = {}
    for key, value in attrs.items():
        if key.lower() in _REDACT_FIELDS or any(
            sensitive in key.lower() for sensitive in ("token", "secret", "password")
        ):
            result[key] = "[REDACTED]"
        else:
            result[key] = value
    return result
