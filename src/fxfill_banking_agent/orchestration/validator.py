"""Plan validator — deterministic checks on execution plans.

The validator runs before any plan step is executed. It checks:
- All referenced tools exist in the registry
- Steps don't depend on themselves
- Dependency chains are valid (no cycles, no missing deps)
- No step proposes a tool the user isn't authorized to use
- Required user inputs are identified

The validator never calls an LLM and never authorizes side effects.
"""

from __future__ import annotations

from fxfill_banking_agent.orchestration.models import (
    ExecutionPlan,
    PlanStep,
    PlanValidation,
)
from fxfill_banking_agent.tools.registry import ToolRegistry


class PlanValidator:
    """Deterministic plan validator.

    Args:
        tool_registry: Registry of available tools for existence checks.
        max_steps: Maximum allowed steps in a plan (default 15).
        forbidden_tools: Tool names that the planner must never propose.
    """

    def __init__(
        self,
        tool_registry: ToolRegistry | None = None,
        max_steps: int = 15,
        forbidden_tools: list[str] | None = None,
    ) -> None:
        self._registry = tool_registry
        self._max_steps = max_steps
        self._forbidden = forbidden_tools or []

    def validate(self, plan: ExecutionPlan) -> PlanValidation:
        """Validate an execution plan.

        Args:
            plan: The plan to validate.

        Returns:
            A ``PlanValidation`` with errors/warnings and a pass/fail decision.
        """
        errors: list[str] = []
        warnings: list[str] = []

        # ── Step count check ───────────────────────────────────
        if plan.step_count == 0:
            errors.append("Plan must have at least one step")
        if plan.step_count > self._max_steps:
            errors.append(f"Plan has {plan.step_count} steps (max {self._max_steps})")

        # ── Duplicate step IDs ─────────────────────────────────
        step_ids = [s.step_id for s in plan.steps]
        if len(step_ids) != len(set(step_ids)):
            errors.append("Plan contains duplicate step IDs")

        # ── Tool existence ─────────────────────────────────────
        for step in plan.steps:
            for tool in step.tool_candidates:
                if tool in self._forbidden:
                    errors.append(f"Step '{step.step_id}' references forbidden tool '{tool}'")
                elif self._registry is not None and not self._registry.has(tool):
                    errors.append(f"Step '{step.step_id}' references unknown tool '{tool}'")

        # ── Dependency validation ──────────────────────────────
        for step in plan.steps:
            # No self-dependency
            if step.step_id in step.dependencies:
                errors.append(f"Step '{step.step_id}' depends on itself")
            # Dependencies must exist
            for dep in step.dependencies:
                if dep not in step_ids:
                    errors.append(f"Step '{step.step_id}' depends on unknown step '{dep}'")

        # ── Circular dependency detection ──────────────────────
        dep_errors = _detect_cycles(plan.steps)
        errors.extend(dep_errors)

        # ── Goal and completion criteria ───────────────────────
        if not plan.goal.strip():
            errors.append("Plan has no goal")
        if not plan.completion_criteria:
            warnings.append("Plan has no completion criteria — verification may be weak")

        # ── Warnings ───────────────────────────────────────────
        for step in plan.steps:
            if step.risk_level in ("high", "critical") and not plan.required_user_inputs:
                warnings.append(
                    f"Step '{step.step_id}' is high-risk but plan identifies "
                    "no required user inputs"
                )

        reason = "Plan is valid" if not errors else "; ".join(errors)
        return PlanValidation(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            reason=reason,
        )


def _detect_cycles(steps: list[PlanStep]) -> list[str]:
    """Detect circular dependencies in the plan step graph."""
    errors: list[str] = []
    step_ids = {s.step_id for s in steps}

    # Build adjacency: step_id → set of dependencies
    deps: dict[str, set[str]] = {s.step_id: set(s.dependencies) for s in steps}

    # DFS-based cycle detection
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {sid: WHITE for sid in step_ids}

    def _dfs(node: str, path: list[str]) -> bool:
        color[node] = GRAY
        path.append(node)
        for dep in deps.get(node, set()):
            if dep not in color:
                continue  # Unknown dependency (caught elsewhere)
            if color[dep] == GRAY:
                cycle = " → ".join(path[path.index(dep) :] + [dep])
                errors.append(f"Circular dependency: {cycle}")
                return True
            if color[dep] == WHITE:
                if _dfs(dep, path):
                    return True
        path.pop()
        color[node] = BLACK
        return False

    for sid in step_ids:
        if color[sid] == WHITE:
            _dfs(sid, [])

    return errors
