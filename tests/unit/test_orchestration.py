"""Unit tests for Planner–Executor–Verifier orchestration."""

from __future__ import annotations

from fxfill_banking_agent.orchestration.models import (
    ExecutionPlan,
    PlanStep,
    StepResult,
)
from fxfill_banking_agent.orchestration.validator import PlanValidator
from fxfill_banking_agent.orchestration.verifier import StepVerifier


class TestPlanStep:
    def test_step_creation(self) -> None:
        step = PlanStep(step_id="1", objective="Get balance", tool_candidates=["get_balance"])
        assert step.step_id == "1"
        assert step.is_ready
        assert not step.is_terminal

    def test_step_statuses(self) -> None:
        step = PlanStep(step_id="1", objective="test", status="pending")
        assert step.is_ready
        step2 = PlanStep(step_id="2", objective="test", status="done")
        assert step2.is_terminal


class TestExecutionPlan:
    def test_empty_plan(self) -> None:
        plan = ExecutionPlan(plan_id="p1", goal="test")
        assert plan.step_count == 0
        assert plan.is_complete  # vacuously true

    def test_plan_with_steps(self) -> None:
        steps = [
            PlanStep(step_id="1", objective="First"),
            PlanStep(step_id="2", objective="Second", dependencies=["1"]),
        ]
        plan = ExecutionPlan(plan_id="p1", goal="test", steps=steps)
        assert plan.step_count == 2
        assert not plan.is_complete
        assert len(plan.pending_steps) == 2

    def test_done_steps(self) -> None:
        steps = [
            PlanStep(step_id="1", objective="First", status="done"),
            PlanStep(step_id="2", objective="Second", status="done"),
        ]
        plan = ExecutionPlan(plan_id="p1", goal="test", steps=steps)
        assert plan.is_complete
        assert len(plan.done_steps) == 2


class TestPlanValidator:
    def test_empty_plan_fails(self) -> None:
        validator = PlanValidator()
        plan = ExecutionPlan(plan_id="p1", goal="test")
        result = validator.validate(plan)
        assert not result.valid
        assert any("at least one step" in e.lower() for e in result.errors)

    def test_valid_plan_passes(self) -> None:
        from fxfill_banking_agent.tools.models import ToolDefinition
        from fxfill_banking_agent.tools.registry import ToolRegistry

        registry = ToolRegistry([ToolDefinition(name="get_balance", description="Get balance")])
        validator = PlanValidator(registry)
        steps = [PlanStep(step_id="1", objective="Check", tool_candidates=["get_balance"])]
        plan = ExecutionPlan(
            plan_id="p1", goal="Check balance", steps=steps, completion_criteria=["balance"]
        )
        result = validator.validate(plan)
        assert result.valid, result.reason

    def test_unknown_tool_fails(self) -> None:
        from fxfill_banking_agent.tools.models import ToolDefinition
        from fxfill_banking_agent.tools.registry import ToolRegistry

        registry = ToolRegistry([ToolDefinition(name="get_balance", description="Get balance")])
        validator = PlanValidator(registry)
        steps = [PlanStep(step_id="1", objective="Bad", tool_candidates=["nonexistent"])]
        plan = ExecutionPlan(plan_id="p1", goal="test", steps=steps)
        result = validator.validate(plan)
        assert not result.valid

    def test_circular_dependency_fails(self) -> None:
        validator = PlanValidator()
        steps = [
            PlanStep(step_id="1", objective="A", dependencies=["2"]),
            PlanStep(step_id="2", objective="B", dependencies=["1"]),
        ]
        plan = ExecutionPlan(plan_id="p1", goal="test", steps=steps)
        result = validator.validate(plan)
        assert not result.valid
        assert any("circular" in e.lower() for e in result.errors)

    def test_self_dependency_fails(self) -> None:
        validator = PlanValidator()
        steps = [PlanStep(step_id="1", objective="A", dependencies=["1"])]
        plan = ExecutionPlan(plan_id="p1", goal="test", steps=steps)
        result = validator.validate(plan)
        assert not result.valid

    def test_forbidden_tool_fails(self) -> None:
        from fxfill_banking_agent.tools.models import ToolDefinition
        from fxfill_banking_agent.tools.registry import ToolRegistry

        registry = ToolRegistry([ToolDefinition(name="submit_transfer", description="Submit")])
        validator = PlanValidator(registry, forbidden_tools=["submit_transfer"])
        steps = [PlanStep(step_id="1", objective="Send", tool_candidates=["submit_transfer"])]
        plan = ExecutionPlan(plan_id="p1", goal="test", steps=steps)
        result = validator.validate(plan)
        assert not result.valid

    def test_too_many_steps_fails(self) -> None:
        validator = PlanValidator(max_steps=3)
        steps = [PlanStep(step_id=str(i), objective=f"Step {i}") for i in range(5)]
        plan = ExecutionPlan(plan_id="p1", goal="test", steps=steps)
        result = validator.validate(plan)
        assert not result.valid

    def test_duplicate_step_ids_fails(self) -> None:
        validator = PlanValidator()
        steps = [
            PlanStep(step_id="1", objective="A"),
            PlanStep(step_id="1", objective="B"),
        ]
        plan = ExecutionPlan(plan_id="p1", goal="test", steps=steps)
        result = validator.validate(plan)
        assert not result.valid
        assert any("duplicate" in e.lower() for e in result.errors)


class TestStepVerifier:
    def test_successful_step_passes(self) -> None:
        verifier = StepVerifier()
        step = PlanStep(step_id="1", objective="test")
        result = StepResult(step_id="1", success=True, output="balance: $100")
        verdict = verifier.verify(step, result)
        assert verdict.passed
        assert verdict.action == "continue"

    def test_failed_step_does_not_pass(self) -> None:
        verifier = StepVerifier()
        step = PlanStep(step_id="1", objective="test")
        result = StepResult(step_id="1", success=False, error="timeout")
        verdict = verifier.verify(step, result)
        assert not verdict.passed

    def test_critical_failure_suggests_ask_user(self) -> None:
        verifier = StepVerifier()
        step = PlanStep(step_id="1", objective="test", risk_level="critical")
        result = StepResult(step_id="1", success=False, error="denied")
        verdict = verifier.verify(step, result)
        assert not verdict.passed
        assert verdict.action == "ask_user"

    def test_retry_for_retriable_step(self) -> None:
        verifier = StepVerifier()
        step = PlanStep(step_id="1", objective="test", max_retries=2)
        result = StepResult(step_id="1", success=False, error="timeout")
        verdict = verifier.verify(step, result)
        assert not verdict.passed
        assert verdict.action == "retry"
