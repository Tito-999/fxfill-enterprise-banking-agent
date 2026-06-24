"""Orchestration data models — plans, steps, validation, and results.

All types are immutable where possible. Plan steps are explicit and
machine-verifiable. The planner proposes; the validator checks; the
executor runs; the verifier confirms.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal


class PlanStatus(str, Enum):
    """Lifecycle status of a plan."""

    DRAFT = "draft"
    VALIDATED = "validated"
    REJECTED = "rejected"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    REPLANNING = "replanning"


@dataclass(frozen=True)
class PlanStep:
    """A single step in an execution plan.

    Attributes:
        step_id: Unique step identifier within the plan.
        objective: Human-readable description of what this step does.
        tool_candidates: Tools that could satisfy this step.
        dependencies: Steps that must complete before this one.
        risk_level: Inherent risk of this step.
        status: Current execution status.
        expected_output_schema: Expected shape of the tool result (optional).
        max_retries: Maximum retries for this step.
    """

    step_id: str
    objective: str
    tool_candidates: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    risk_level: Literal["low", "medium", "high", "critical"] = "low"
    status: Literal["pending", "running", "done", "failed", "blocked"] = "pending"
    expected_output_schema: dict[str, Any] | None = None
    max_retries: int = 1

    @property
    def is_ready(self) -> bool:
        """True when this step is pending and has no incomplete dependencies."""
        return self.status == "pending"

    @property
    def is_terminal(self) -> bool:
        """True when this step is in a terminal state."""
        return self.status in ("done", "failed")


@dataclass(frozen=True)
class ExecutionPlan:
    """A structured plan for completing a complex banking task.

    Attributes:
        plan_id: Unique plan identifier.
        goal: The user's expressed goal in their own words.
        assumptions: Explicit assumptions the plan is based on.
        required_user_inputs: Information that must come from the user.
        steps: Ordered list of plan steps.
        completion_criteria: Criteria that must be met for the plan to succeed.
        max_replans: Maximum number of replanning attempts.
        status: Current lifecycle status.
    """

    plan_id: str
    goal: str
    assumptions: list[str] = field(default_factory=list)
    required_user_inputs: list[str] = field(default_factory=list)
    steps: list[PlanStep] = field(default_factory=list)
    completion_criteria: list[str] = field(default_factory=list)
    max_replans: int = 2
    status: PlanStatus = PlanStatus.DRAFT

    @property
    def pending_steps(self) -> list[PlanStep]:
        """Return steps that are ready to execute."""
        return [s for s in self.steps if s.is_ready]

    @property
    def done_steps(self) -> list[PlanStep]:
        """Return completed steps."""
        return [s for s in self.steps if s.status == "done"]

    @property
    def failed_steps(self) -> list[PlanStep]:
        """Return failed steps."""
        return [s for s in self.steps if s.status == "failed"]

    @property
    def step_count(self) -> int:
        """Total number of steps."""
        return len(self.steps)

    @property
    def is_complete(self) -> bool:
        """True when all steps are done."""
        return all(s.status == "done" for s in self.steps)


@dataclass(frozen=True)
class PlanValidation:
    """Result of validating an execution plan.

    Attributes:
        valid: True when the plan passes all checks.
        errors: List of validation errors.
        warnings: Non-fatal concerns.
        reason: Human-readable explanation.
    """

    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    reason: str = ""


@dataclass(frozen=True)
class StepResult:
    """Result of executing a single plan step.

    Attributes:
        step_id: Which step was executed.
        success: Whether the execution succeeded.
        tool_name: The tool that was called.
        output: The tool's output (if successful).
        error: Error message (if failed).
        duration_ms: Wall-clock duration.
    """

    step_id: str
    success: bool
    tool_name: str = ""
    output: str = ""
    error: str = ""
    duration_ms: float = 0.0


@dataclass(frozen=True)
class VerificationResult:
    """Result of verifying a step's outcome.

    Attributes:
        passed: True when the step meets all verification criteria.
        step_id: Which step was verified.
        reason: Human-readable explanation.
        action: What to do next — continue, retry, ask_user, replan, abort.
    """

    passed: bool
    step_id: str
    reason: str = ""
    action: Literal["continue", "retry", "ask_user", "replan", "abort"] = "continue"
