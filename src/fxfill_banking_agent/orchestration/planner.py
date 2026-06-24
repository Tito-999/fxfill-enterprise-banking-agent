"""Planner — generates structured execution plans for complex tasks.

The planner uses the LLM to decompose a user goal into validated steps.
It never executes tools and never authorizes side effects.

The planner's output is always validated by ``PlanValidator`` before
any step is executed.
"""

from __future__ import annotations

import uuid
from typing import Any

from fxfill_banking_agent.llm import LLMProvider
from fxfill_banking_agent.logging import get_logger
from fxfill_banking_agent.orchestration.models import (
    ExecutionPlan,
    PlanStatus,
)
from fxfill_banking_agent.orchestration.validator import PlanValidator
from fxfill_banking_agent.tools.registry import ToolRegistry

logger = get_logger(__name__)

# ── Planner prompt template ─────────────────────────────────────────
_PLANNER_SYSTEM = """You are a banking task planner. Given a user's goal and available tools,
produce a structured execution plan as JSON.

Rules:
- Each step must reference only tools that exist in the tool list.
- Steps must be ordered — a step's dependencies must be earlier steps.
- Identify assumptions you're making and information you need from the user.
- Never propose tools the user is not authorized to use.
- For high-risk steps, flag them with risk_level "high" or "critical".
- Max 10 steps.

Output ONLY valid JSON:
{
  "assumptions": ["..."],
  "required_user_inputs": ["..."],
  "steps": [
    {
      "step_id": "1",
      "objective": "...",
      "tool_candidates": ["tool_name"],
      "dependencies": [],
      "risk_level": "low"
    }
  ],
  "completion_criteria": ["..."]
}"""


class Planner:
    """Generates structured execution plans using LLM reasoning.

    The planner proposes; the validator checks. The planner never
    executes tools and never authorizes side effects.

    Args:
        llm: Language model provider for plan generation.
        tool_registry: Available tools for plan step candidates.
        validator: Plan validator (created automatically if not provided).
        max_retries: Maximum plan generation retries on validation failure.
    """

    def __init__(
        self,
        llm: LLMProvider,
        tool_registry: ToolRegistry | None = None,
        validator: PlanValidator | None = None,
        max_retries: int = 3,
    ) -> None:
        self._llm = llm
        self._tool_registry = tool_registry
        self._validator = validator or PlanValidator(tool_registry)
        self._max_retries = max_retries

    async def plan(self, goal: str, context: str = "") -> ExecutionPlan:
        """Generate an execution plan for a user goal.

        Args:
            goal: The user's expressed goal.
            context: Additional context (e.g., conversation history, account info).

        Returns:
            An ``ExecutionPlan``. May be in DRAFT or REJECTED status.

        The caller must validate the plan before executing any steps.
        """
        plan_id = str(uuid.uuid4())[:8]

        # Build tool list for the prompt
        tool_names: list[str] = []
        if self._tool_registry is not None:
            tool_names = sorted(self._tool_registry.names)

        user_prompt = (
            f"Goal: {goal}\n"
            f"Available tools: {', '.join(tool_names) if tool_names else 'unknown'}\n"
            f"Context: {context}\n\n"
            "Generate a step-by-step execution plan as JSON."
        )

        for attempt in range(self._max_retries):
            try:
                plan = await self._generate_plan(plan_id, goal, user_prompt)
                validation = self._validator.validate(plan)
                if validation.valid:
                    plan = ExecutionPlan(
                        plan_id=plan.plan_id,
                        goal=plan.goal,
                        assumptions=plan.assumptions,
                        required_user_inputs=plan.required_user_inputs,
                        steps=plan.steps,
                        completion_criteria=plan.completion_criteria,
                        max_replans=plan.max_replans,
                        status=PlanStatus.VALIDATED,
                    )
                    logger.info("plan_generated", plan_id=plan_id, steps=plan.step_count)
                    return plan

                logger.warning(
                    "plan_validation_failed",
                    attempt=attempt + 1,
                    errors=validation.errors,
                )
            except Exception as exc:
                logger.warning("plan_generation_error", attempt=attempt + 1, error=str(exc))

        # All retries exhausted
        return ExecutionPlan(
            plan_id=plan_id,
            goal=goal,
            status=PlanStatus.REJECTED,
        )

    async def _generate_plan(self, plan_id: str, goal: str, user_prompt: str) -> ExecutionPlan:
        """Call the LLM and parse the plan JSON."""
        from langchain_core.messages import HumanMessage, SystemMessage

        messages: list[Any] = [
            SystemMessage(content=_PLANNER_SYSTEM),
            HumanMessage(content=user_prompt),
        ]

        response = await self._llm.invoke(messages, tools=None, tool_choice="none")
        raw = str(getattr(response, "content", ""))

        # Extract JSON from markdown fenced code blocks if present
        json_str = _extract_json(raw)

        import json

        data = json.loads(json_str)

        from fxfill_banking_agent.orchestration.models import PlanStep

        steps = [
            PlanStep(
                step_id=s.get("step_id", str(i + 1)),
                objective=s.get("objective", ""),
                tool_candidates=s.get("tool_candidates", []),
                dependencies=s.get("dependencies", []),
                risk_level=s.get("risk_level", "low"),
            )
            for i, s in enumerate(data.get("steps", []))
        ]

        return ExecutionPlan(
            plan_id=plan_id,
            goal=goal,
            assumptions=data.get("assumptions", []),
            required_user_inputs=data.get("required_user_inputs", []),
            steps=steps,
            completion_criteria=data.get("completion_criteria", []),
            status=PlanStatus.DRAFT,
        )


def _extract_json(text: str) -> str:
    """Extract JSON from text, handling markdown code fences."""
    import re

    # Try ```json ... ``` block first
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if match:
        return match.group(1).strip()

    # Fall back to first { ... } block
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        return match.group(0).strip()

    return text.strip()
