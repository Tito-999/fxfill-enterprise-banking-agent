"""Per-step cost and latency metrics for the banking agent.

Tracks token usage, wall-clock duration, and tool-call counts so
that runs can be compared and tuned.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class StepMetrics:
    """Metrics for a single agent step.

    Attributes:
        step_index: Zero-based step number within the run.
        duration_ms: Wall-clock duration in milliseconds.
        input_tokens: Estimated input tokens for this step.
        output_tokens: Estimated output tokens for this step.
        tool_call_count: Number of tool calls executed in this step.
        tool_duration_ms: Total time spent in tool execution.
    """

    step_index: int
    duration_ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    tool_call_count: int = 0
    tool_duration_ms: float = 0.0


@dataclass
class RunMetrics:
    """Aggregated metrics for a complete agent run.

    Attributes:
        run_id: Unique identifier for the run.
        steps: Per-step metrics.
        total_duration_ms: Sum of all step durations.
        total_input_tokens: Sum of input tokens.
        total_output_tokens: Sum of output tokens.
        total_tool_calls: Total number of tool calls.
        started_at: ISO-8601 start timestamp.
        completed_at: ISO-8601 completion timestamp.
    """

    run_id: str
    steps: list[StepMetrics] = field(default_factory=list)
    total_duration_ms: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_tool_calls: int = 0
    started_at: str = ""
    completed_at: str = ""


class MetricsCollector(Protocol):
    """Protocol for collecting and aggregating step metrics."""

    def start_run(self, run_id: str) -> None:
        """Begin collecting metrics for a run."""
        ...

    def record_step(self, metrics: StepMetrics) -> None:
        """Record metrics for a single step."""
        ...

    def finish_run(self) -> RunMetrics:
        """Finalize and return the run's aggregate metrics."""
        ...


class InMemoryMetricsCollector:
    """Simple in-memory collector for development and testing."""

    def __init__(self) -> None:
        self._current: RunMetrics | None = None
        self._start_time: float = 0.0

    def start_run(self, run_id: str) -> None:
        """Begin collecting metrics for a run."""
        from datetime import datetime, timezone

        self._current = RunMetrics(
            run_id=run_id,
            started_at=datetime.now(timezone.utc).isoformat(),
        )
        self._start_time = time.monotonic()

    def record_step(self, metrics: StepMetrics) -> None:
        """Record metrics for a single step."""
        if not self._current:
            raise RuntimeError("No active run — call start_run first")
        self._current.steps.append(metrics)
        self._current.total_input_tokens += metrics.input_tokens
        self._current.total_output_tokens += metrics.output_tokens
        self._current.total_tool_calls += metrics.tool_call_count
        self._current.total_duration_ms += metrics.duration_ms

    def finish_run(self) -> RunMetrics:
        """Finalize and return the run's aggregate metrics."""
        from datetime import datetime, timezone

        if not self._current:
            raise RuntimeError("No active run — call start_run first")
        self._current.total_duration_ms = (time.monotonic() - self._start_time) * 1000
        self._current.completed_at = datetime.now(timezone.utc).isoformat()
        result = self._current
        self._current = None
        return result
