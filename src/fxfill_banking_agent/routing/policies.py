"""Routing policies — maps intents to execution strategies.

The policy layer is deterministic. It takes an IntentResult and returns
a Route that tells the agent which execution path to follow.

Routes:
- ``DIRECT``: Execute tools directly in a single step (no LLM reasoning loop)
- ``RAG``: Retrieve knowledge, then respond
- ``PLANNER``: Full Planner–Executor–Verifier workflow
- ``TRANSFER_STATE_MACHINE``: Structured transfer lifecycle
- ``REJECT``: Refuse the request with a safe message
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from fxfill_banking_agent.routing.intent import Intent, IntentResult


class RouteKind(str, Enum):
    """Available execution paths."""

    DIRECT = "direct"  # Single-step tool execution, no reasoning loop
    RAG = "rag"  # Retrieve knowledge, then respond
    PLANNER = "planner"  # Full Planner–Executor–Verifier
    TRANSFER_STATE_MACHINE = "transfer_state_machine"  # Structured transfer workflow
    REJECT = "reject"  # Unsupported or out-of-scope


@dataclass(frozen=True)
class Route:
    """A routing decision that maps an intent to an execution strategy.

    Attributes:
        kind: Which execution path to take.
        intent: The classified intent.
        reason: Why this route was chosen.
        max_steps: Override for max agent steps (PLANNER only).
        require_approval: Force human approval for this route.
        suggested_tools: Tools likely relevant to this intent.
    """

    kind: RouteKind
    intent: Intent
    reason: str = ""
    max_steps: int | None = None
    require_approval: bool = False
    suggested_tools: list[str] | None = None


class RoutingPolicy:
    """Deterministic mapping from intent to execution route.

    The policy is simple and explicit. Complex intents go to PLANNER,
    simple reads go to DIRECT, knowledge questions go to RAG.

    This policy never calls an LLM and never authorizes side effects.
    """

    # Route mapping — the single source of truth
    _ROUTES: dict[Intent, RouteKind] = {
        # Simple reads → direct tool workflow
        Intent.ACCOUNT_QUERY: RouteKind.DIRECT,
        Intent.TRANSACTION_QUERY: RouteKind.DIRECT,
        Intent.BENEFICIARY_QUERY: RouteKind.DIRECT,
        Intent.TRANSFER_STATUS: RouteKind.DIRECT,
        # Transfer lifecycle → state machine
        Intent.TRANSFER_CREATE: RouteKind.TRANSFER_STATE_MACHINE,
        Intent.TRANSFER_SUBMIT: RouteKind.TRANSFER_STATE_MACHINE,
        Intent.TRANSFER_CANCEL: RouteKind.TRANSFER_STATE_MACHINE,
        # Knowledge → RAG
        Intent.POLICY_QUESTION: RouteKind.RAG,
        Intent.FORM_ASSISTANCE: RouteKind.RAG,
        Intent.PRODUCT_QUESTION: RouteKind.RAG,
        # Complex → Planner
        Intent.COMPLEX_TASK: RouteKind.PLANNER,
        Intent.MULTI_ACCOUNT_TASK: RouteKind.PLANNER,
        # High-risk → Planner with mandatory approval
        Intent.SUSPICIOUS_ACTIVITY_REPORT: RouteKind.PLANNER,
        # Unsupported → reject gracefully
        Intent.GENERAL_UNSUPPORTED: RouteKind.REJECT,
    }

    def route(self, result: IntentResult) -> Route:
        """Return the execution route for a classified intent.

        Args:
            result: The classified intent result.

        Returns:
            A ``Route`` with the execution strategy.
        """
        kind = self._ROUTES.get(result.intent, RouteKind.REJECT)
        reason = f"{result.intent.value} → {kind.value}"

        route = Route(
            kind=kind,
            intent=result.intent,
            reason=reason,
            suggested_tools=result.suggested_tools if result.suggested_tools else None,
            require_approval=result.is_high_risk,
        )

        # PLANNER routes get a default max_steps cap
        if kind == RouteKind.PLANNER:
            route = Route(
                kind=kind,
                intent=result.intent,
                reason=reason,
                max_steps=20,
                require_approval=result.is_high_risk,
                suggested_tools=result.suggested_tools if result.suggested_tools else None,
            )

        return route
