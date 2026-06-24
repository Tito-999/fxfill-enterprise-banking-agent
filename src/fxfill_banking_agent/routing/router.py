"""Main router — classifies intent and dispatches to the correct execution path.

The router is the entry point for every user request. It:
1. Classifies the user's intent
2. Determines the execution route
3. Returns a route decision that the agent runtime follows

Simple queries must never go through expensive Planner loops.
High-risk operations always go through policy validation.
"""

from __future__ import annotations

from typing import Any

from fxfill_banking_agent.routing.classifier import classify
from fxfill_banking_agent.routing.intent import IntentResult
from fxfill_banking_agent.routing.policies import Route, RoutingPolicy


class Router:
    """Routes user requests to the appropriate execution strategy.

    Composes intent classification and routing policy into a single
    call that the agent runtime can use to decide how to execute.

    Args:
        policy: Optional custom routing policy. Uses default if None.
        llm: Optional LLM for fallback intent classification. When None,
            only deterministic keyword matching is used.
    """

    def __init__(
        self,
        policy: RoutingPolicy | None = None,
        llm: Any = None,
    ) -> None:
        self._policy = policy or RoutingPolicy()
        self._llm = llm

    def classify(self, message: str) -> IntentResult:
        """Classify a user message into an intent.

        Uses deterministic keyword matching first. Falls back to LLM
        classification only if an LLM provider is configured.
        """
        return classify(message, llm=self._llm)

    def route(self, message: str) -> Route:
        """Classify and route a user message in one call.

        Args:
            message: The user's natural language message.

        Returns:
            A ``Route`` describing which execution path to follow.
        """
        intent_result = self.classify(message)
        return self._policy.route(intent_result)

    def route_from_intent(self, intent_result: IntentResult) -> Route:
        """Determine the route for an already-classified intent."""
        return self._policy.route(intent_result)
