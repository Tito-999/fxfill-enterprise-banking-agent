"""AgentOps — shadow/canary deployment, drift monitoring, cost governance (P3/Stage C).

Provides the models and interfaces for safe gradual rollout and continuous
production improvement. All features are scaffolded for local testing;
production deployment requires real infrastructure.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class TrafficMode(str, Enum):
    """Traffic allocation modes for staged rollout."""

    OFFLINE = "offline"  # Not serving traffic
    SHADOW = "shadow"  # Receives copy of traffic, side effects suppressed
    INTERNAL_PILOT = "internal_pilot"  # Internal users only
    CANARY = "canary"  # Small percentage of real traffic
    FULL_ROLLOUT = "full_rollout"  # All traffic


@dataclass(frozen=True)
class TrafficPolicy:
    """Controls how traffic is allocated between baseline and candidate.

    Shadow mode: candidate receives traffic copies but ALL writes are
    suppressed. Used to compare outputs safely.
    """

    mode: TrafficMode = TrafficMode.OFFLINE
    candidate_percent: float = 0.0  # 0.0–100.0
    tenant_allowlist: list[str] = field(default_factory=list)
    write_kill_switch: bool = False  # Global override: block all writes


@dataclass
class DriftThreshold:
    """Threshold for triggering drift alerts.

    When a metric exceeds its threshold, an alert fires. Drift never
    triggers silent adaptation — it always requires human review.
    """

    metric_name: str
    warning_threshold: float = 0.10  # 10% deviation = warning
    critical_threshold: float = 0.25  # 25% deviation = critical
    current_baseline: float = 0.0
    current_value: float = 0.0

    @property
    def deviation(self) -> float:
        if self.current_baseline == 0:
            return 0.0
        return abs(self.current_value - self.current_baseline) / self.current_baseline

    @property
    def status(self) -> str:
        if self.deviation >= self.critical_threshold:
            return "critical"
        if self.deviation >= self.warning_threshold:
            return "warning"
        return "ok"


@dataclass
class CostReport:
    """Per-task cost attribution."""

    task_id: str
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    tool_calls: int = 0
    duration_ms: float = 0.0
    estimated_cost_usd: float = 0.0
    cache_hit: bool = False


@dataclass
class IncidentRecord:
    """Record of a production incident."""

    incident_id: str
    severity: str = "low"  # low, medium, high, critical
    title: str = ""
    timeline: list[str] = field(default_factory=list)
    kill_switch_activated: bool = False
    rollback_target: str = ""
    resolved: bool = False
    postmortem_url: str = ""


# ── Write kill switch ────────────────────────────────────────────────


class WriteKillSwitch:
    """Global kill switch for all write/side-effecting operations.

    When activated, all write tools return errors. Read operations
    continue normally. Used during incidents or detected anomalies.
    """

    def __init__(self) -> None:
        self._active = False
        self._activated_at: str = ""
        self._reason: str = ""

    @property
    def is_active(self) -> bool:
        return self._active

    def activate(self, reason: str) -> None:
        from datetime import datetime, timezone

        self._active = True
        self._reason = reason
        self._activated_at = datetime.now(timezone.utc).isoformat()

    def deactivate(self) -> None:
        self._active = False
        self._reason = ""

    def check(self, tool_name: str, side_effect: bool) -> bool:
        """Return True if the tool call is allowed. False = blocked."""
        if not self._active:
            return True
        if not side_effect:
            return True  # Reads still allowed
        return False  # Writes blocked
