"""Intent routing — classify user requests and dispatch to the right workflow.

The router ensures simple queries don't waste resources on complex
Planner–Executor pipelines, and high-risk operations get the appropriate
policy enforcement.

Components:
- ``Intent``: Enum of recognized intent categories
- ``IntentClassifier``: Deterministic keyword + lightweight model classifier
- ``RoutingPolicy``: Maps intents to execution strategies
- ``Router``: Main dispatch that routes to direct/RAG/Planner paths
"""

from fxfill_banking_agent.routing.classifier import classify
from fxfill_banking_agent.routing.intent import Intent, IntentConfidence, IntentResult
from fxfill_banking_agent.routing.policies import Route, RouteKind, RoutingPolicy
from fxfill_banking_agent.routing.router import Router

__all__ = [
    "Intent",
    "IntentResult",
    "IntentConfidence",
    "classify",
    "RoutingPolicy",
    "Route",
    "RouteKind",
    "Router",
]
