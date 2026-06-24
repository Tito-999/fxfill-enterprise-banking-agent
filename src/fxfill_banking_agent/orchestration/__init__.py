"""Orchestration — Planner–Executor–Verifier workflow for complex tasks.

The orchestration layer decomposes complex multi-step banking tasks into
validated, executable plans. It enforces hard limits on steps, replans,
tool calls, tokens, and wall time.

Security invariants:
- Planner proposes plans but cannot execute tools.
- Executor executes only validated steps through the authorization gateway.
- Verifier checks results with deterministic rules — never uses natural
  language to override deterministic tool failures.
- Replans never reuse a previously denied grant.
"""

from fxfill_banking_agent.orchestration.executor import StepExecutor
from fxfill_banking_agent.orchestration.models import (
    ExecutionPlan,
    PlanStatus,
    PlanStep,
    PlanValidation,
    StepResult,
    VerificationResult,
)
from fxfill_banking_agent.orchestration.planner import Planner
from fxfill_banking_agent.orchestration.validator import PlanValidator
from fxfill_banking_agent.orchestration.verifier import StepVerifier

__all__ = [
    "ExecutionPlan",
    "PlanStep",
    "PlanStatus",
    "PlanValidation",
    "StepResult",
    "VerificationResult",
    "Planner",
    "PlanValidator",
    "StepExecutor",
    "StepVerifier",
]
