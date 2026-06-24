"""Reliability engineering — SLOs, HA, DR, circuit breakers, chaos testing (P2-06).

Defines measurable SLOs, degraded mode states, and reconciliation
interfaces. All SLOs must be verified by actual measurement, not
assumed from code structure.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ServiceState(str, Enum):
    """Operational state of a service component."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"  # Some functionality limited
    READ_ONLY = "read_only"  # All writes blocked
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class SLO:
    """A Service Level Objective with measurement window.

    Attributes:
        name: Human-readable SLO name.
        target_percent: Target success rate (e.g. 99.9).
        measurement_window_days: Rolling window for measurement.
        current_value: Most recent measured value.
    """

    name: str
    target_percent: float = 99.9
    measurement_window_days: int = 30
    current_value: float | None = None


# ── Default SLOs (targets only — must be verified in production) ────

DEFAULT_SLOS: list[SLO] = [
    SLO("api_availability", target_percent=99.9),
    SLO("read_task_success_rate", target_percent=99.5),
    SLO("write_task_exactly_once_rate", target_percent=99.99),
    SLO("approval_resume_success_rate", target_percent=99.9),
    SLO("p95_latency_ms", target_percent=95.0),
    SLO("audit_event_loss_rate", target_percent=0.01),
]


# ── Circuit breaker ──────────────────────────────────────────────────


class CircuitState(str, Enum):
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing fast
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class CircuitBreaker:
    """Simple circuit breaker for external service calls.

    Not for production use — demonstrates the pattern. Production
    should use a battle-tested library (e.g. pybreaker, resilience4j).
    """

    name: str
    failure_threshold: int = 5
    recovery_timeout_seconds: float = 30.0
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    last_failure_time: float = 0.0

    def record_success(self) -> None:

        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.CLOSED
            self.failure_count = 0
        elif self.state == CircuitState.CLOSED:
            self.failure_count = 0

    def record_failure(self) -> None:
        import time

        self.failure_count += 1
        self.last_failure_time = time.monotonic()
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN

    def allow_request(self) -> bool:
        import time

        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.OPEN:
            if time.monotonic() - self.last_failure_time > self.recovery_timeout_seconds:
                self.state = CircuitState.HALF_OPEN
                return True
            return False
        # HALF_OPEN: allow one probe request
        return True


# ── Reconciliation ───────────────────────────────────────────────────


@dataclass(frozen=True)
class ReconciliationTask:
    """A task for the reconciliation worker.

    Created when a tool outcome is UNKNOWN — the worker queries the
    upstream system to determine what actually happened.
    """

    task_id: str
    idempotency_key: str
    tool_name: str
    session_id: str = ""
    created_at: str = ""
    retry_count: int = 0
    max_retries: int = 5
    resolved: bool = False
    resolution: str = ""  # "succeeded", "failed", "still_unknown"


# ── Chaos test scenarios ────────────────────────────────────────────

CHAOS_SCENARIOS: list[dict[str, Any]] = [
    {
        "name": "llm_provider_timeout",
        "description": "LLM returns 429/500 — circuit breaker opens, fallback model used",
    },
    {
        "name": "tool_gateway_timeout",
        "description": "MCP tool call times out — UNKNOWN outcome, reconciliation queued",
    },
    {
        "name": "postgres_failover",
        "description": "Primary PostgreSQL fails — reads continue from replica, writes queued",
    },
    {
        "name": "redis_unavailable",
        "description": "Redis down — rate limits and cache gracefully degraded",
    },
    {
        "name": "crash_before_approval",
        "description": "Pod crashes after interrupt, before HITL — resume from checkpoint",
    },
    {
        "name": "crash_after_approval",
        "description": "Pod crashes after approval dispatch — idempotency prevents double execution",
    },
    {
        "name": "duplicate_webhook",
        "description": "Same webhook delivered twice — idempotency key deduplication",
    },
    {
        "name": "clock_skew",
        "description": "System clock jumps — timestamps still monotonically ordered in audit",
    },
]
