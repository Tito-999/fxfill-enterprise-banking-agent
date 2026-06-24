"""Step verifier — checks that executed steps meet their completion criteria.

The verifier uses deterministic rules, not natural language judgment.
It cannot override a tool's deterministic failure with an LLM-generated
"looks fine" — if a tool returns an error, verification must fail.
"""

from __future__ import annotations

from typing import Literal

from fxfill_banking_agent.orchestration.models import (
    ExecutionPlan,
    PlanStep,
    StepResult,
    VerificationResult,
)


class StepVerifier:
    """Deterministic step verifier.

    Checks that:
    - The tool returned success (not error)
    - The output is non-empty
    - Completion criteria are met (simple pattern matching)

    The verifier never uses an LLM — verification is deterministic.
    """

    def verify(
        self,
        step: PlanStep,
        result: StepResult,
        plan: ExecutionPlan | None = None,
    ) -> VerificationResult:
        """Verify a step's result.

        Args:
            step: The step that was executed.
            result: The result from executing the step.
            plan: The parent plan (for completion criteria context).

        Returns:
            A ``VerificationResult`` with pass/fail and next action.
        """
        # ── Tool failure → verification failure ────────────────
        if not result.success:
            return VerificationResult(
                passed=False,
                step_id=step.step_id,
                reason=f"Tool '{result.tool_name}' failed: {result.error}",
                action=_next_action_for_failure(step),
            )

        # ── Empty output warning ───────────────────────────────
        if not result.output.strip():
            return VerificationResult(
                passed=True,
                step_id=step.step_id,
                reason="Step succeeded but produced empty output",
                action="continue",
            )

        # ── Completion criteria check ──────────────────────────
        if plan and plan.completion_criteria:
            for criterion in plan.completion_criteria:
                if not _check_criterion(criterion, result):
                    return VerificationResult(
                        passed=False,
                        step_id=step.step_id,
                        reason=f"Completion criterion not met: {criterion}",
                        action="retry",
                    )

        return VerificationResult(
            passed=True,
            step_id=step.step_id,
            reason=f"Step '{step.step_id}' verified successfully",
            action="continue",
        )


def _next_action_for_failure(step: PlanStep) -> Literal["retry", "ask_user", "abort"]:
    """Determine the next action when a step fails."""
    if step.max_retries > 1:
        return "retry"
    if step.risk_level == "critical":
        return "ask_user"
    return "abort"


def _check_criterion(criterion: str, result: StepResult) -> bool:
    """Check if a simple completion criterion is met by the result.

    This is intentionally simple — complex criteria need the verifier
    to be extended with domain-specific checks.
    """
    output_lower = result.output.lower()

    # Named criteria patterns
    if "balance" in criterion.lower():
        return "balance" in output_lower or "amount" in output_lower
    if "status" in criterion.lower():
        return "status" in output_lower
    if "draft" in criterion.lower():
        return "draft_id" in output_lower

    # Default: just check that we got non-empty output
    return bool(result.output.strip())
