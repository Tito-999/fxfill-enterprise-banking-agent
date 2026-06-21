"""Tests for metrics collection."""

from __future__ import annotations

import pytest

from fxfill_banking_agent.metrics import InMemoryMetricsCollector, StepMetrics


class TestInMemoryMetricsCollector:
    @pytest.mark.asyncio
    async def test_empty_run(self) -> None:
        collector = InMemoryMetricsCollector()
        collector.start_run("test-run")
        result = collector.finish_run()

        assert result.run_id == "test-run"
        assert result.steps == []
        assert result.total_input_tokens == 0
        assert result.total_output_tokens == 0
        assert result.total_tool_calls == 0
        assert result.started_at
        assert result.completed_at
        assert result.total_duration_ms >= 0

    @pytest.mark.asyncio
    async def test_single_step(self) -> None:
        collector = InMemoryMetricsCollector()
        collector.start_run("r1")
        collector.record_step(
            StepMetrics(
                step_index=0,
                duration_ms=100.0,
                input_tokens=50,
                output_tokens=20,
            )
        )
        result = collector.finish_run()

        assert len(result.steps) == 1
        assert result.total_input_tokens == 50
        assert result.total_output_tokens == 20
        assert result.steps[0].duration_ms == 100.0

    @pytest.mark.asyncio
    async def test_multiple_steps_aggregate(self) -> None:
        collector = InMemoryMetricsCollector()
        collector.start_run("r1")
        collector.record_step(
            StepMetrics(
                step_index=0,
                duration_ms=50.0,
                input_tokens=10,
                output_tokens=5,
            )
        )
        collector.record_step(
            StepMetrics(
                step_index=1,
                duration_ms=75.0,
                input_tokens=20,
                output_tokens=10,
                tool_call_count=1,
                tool_duration_ms=30.0,
            )
        )
        collector.record_step(
            StepMetrics(
                step_index=2,
                duration_ms=25.0,
                input_tokens=5,
                output_tokens=3,
            )
        )
        result = collector.finish_run()

        assert len(result.steps) == 3
        assert result.total_duration_ms > 0  # elapsed wall-clock
        assert result.total_input_tokens == 35
        assert result.total_output_tokens == 18
        assert result.total_tool_calls == 1

    @pytest.mark.asyncio
    async def test_no_active_run_raises(self) -> None:
        collector = InMemoryMetricsCollector()
        with pytest.raises(RuntimeError, match="No active run"):
            collector.record_step(StepMetrics(step_index=0))

        with pytest.raises(RuntimeError, match="No active run"):
            collector.finish_run()

    @pytest.mark.asyncio
    async def test_tool_metrics_tracked(self) -> None:
        collector = InMemoryMetricsCollector()
        collector.start_run("r1")
        collector.record_step(
            StepMetrics(
                step_index=0,
                duration_ms=200.0,
                tool_call_count=3,
                tool_duration_ms=150.0,
            )
        )
        result = collector.finish_run()
        assert result.total_tool_calls == 3
        assert result.steps[0].tool_duration_ms == 150.0
