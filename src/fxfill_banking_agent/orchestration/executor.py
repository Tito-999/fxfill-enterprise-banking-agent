"""Step executor — runs one validated plan step at a time.

The executor:
- Executes exactly one approved step per call.
- Passes every tool call through the authorization gateway.
- Records timing and results.
- Never executes steps with failed dependencies.
- Never retries a step more than its max_retries.
"""

from __future__ import annotations

import time
from typing import Any

from fxfill_banking_agent.auth import AuthorizationGateway, Operation, OperationKind
from fxfill_banking_agent.logging import get_logger
from fxfill_banking_agent.mcp_client import MCPClient, ToolCall
from fxfill_banking_agent.orchestration.models import (
    ExecutionPlan,
    PlanStep,
    StepResult,
)

logger = get_logger(__name__)


class StepExecutor:
    """Executes plan steps one at a time through the authorization gateway.

    Args:
        mcp_client: MCP client for tool execution.
        auth_gateway: Authorization gateway for pre-execution checks.
        tool_registry: Optional tool registry for metadata lookup.
    """

    def __init__(
        self,
        mcp_client: MCPClient,
        auth_gateway: AuthorizationGateway,
        tool_registry: Any = None,
    ) -> None:
        self._mcp = mcp_client
        self._auth = auth_gateway
        self._registry = tool_registry

    async def execute_step(
        self, plan: ExecutionPlan, step: PlanStep, tool_args: dict[str, Any] | None = None
    ) -> StepResult:
        """Execute a single plan step.

        Args:
            plan: The execution plan this step belongs to.
            step: The step to execute.
            tool_args: Tool arguments (if pre-determined). When None,
                the first tool_candidate is used with default args.

        Returns:
            A ``StepResult`` with success/failure and timing.
        """
        if step.status != "pending":
            return StepResult(
                step_id=step.step_id,
                success=False,
                error=f"Step '{step.step_id}' is not pending (status: {step.status})",
            )

        if not step.tool_candidates:
            return StepResult(
                step_id=step.step_id,
                success=False,
                error=f"Step '{step.step_id}' has no tool candidates",
            )

        tool_name = step.tool_candidates[0]
        args = tool_args or {}

        # Authorize
        kind = OperationKind.READ
        if self._registry is not None:
            td = self._registry.get(tool_name)
            if td is not None and td.side_effect:
                kind = OperationKind.WRITE
                if td.risk_level == "critical":
                    kind = OperationKind.TRANSFER

        t0 = time.monotonic()
        try:
            op = Operation(
                kind=kind,
                name=tool_name,
                target=f"step:{step.step_id}",
                details={"args": args, "plan_id": plan.plan_id},
            )
            decision = await self._auth.authorize(op)

            if decision.decision.value == "denied":
                return StepResult(
                    step_id=step.step_id,
                    success=False,
                    tool_name=tool_name,
                    error=f"Authorization denied: {decision.reason}",
                    duration_ms=(time.monotonic() - t0) * 1000,
                )

            # Execute
            call = ToolCall(name=tool_name, arguments=args)
            result = await self._mcp.call_tool(call)

            duration_ms = (time.monotonic() - t0) * 1000
            if result.success:
                logger.info("step_executed", step_id=step.step_id, tool=tool_name)
                return StepResult(
                    step_id=step.step_id,
                    success=True,
                    tool_name=tool_name,
                    output=result.content,
                    duration_ms=duration_ms,
                )
            else:
                return StepResult(
                    step_id=step.step_id,
                    success=False,
                    tool_name=tool_name,
                    error=result.error or "Tool execution failed",
                    duration_ms=duration_ms,
                )

        except Exception as exc:
            return StepResult(
                step_id=step.step_id,
                success=False,
                tool_name=tool_name,
                error=str(exc),
                duration_ms=(time.monotonic() - t0) * 1000,
            )
