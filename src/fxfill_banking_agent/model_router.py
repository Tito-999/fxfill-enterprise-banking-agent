"""Model router — routes requests to the right model tier.

Three tiers:
- Lightweight: Intent classification, field extraction (cheap, fast)
- Standard: General customer service, RAG responses, simple tool calls
- Reasoning: Complex plans, anomaly investigation, multi-constraint tasks

Routing factors: intent, risk level, complexity, context length, SLA, cost budget.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ModelTier(str, Enum):
    """Model capability tiers."""

    LIGHTWEIGHT = "lightweight"  # Fast classifier/small model
    STANDARD = "standard"  # General-purpose
    REASONING = "reasoning"  # Complex reasoning


@dataclass(frozen=True)
class ModelRoute:
    """A model routing decision.

    Attributes:
        tier: Which model tier to use.
        model: Specific model identifier.
        reason: Why this tier was chosen.
        max_tokens: Override for max tokens.
        temperature: Override for temperature.
    """

    tier: ModelTier
    model: str = ""
    reason: str = ""
    max_tokens: int = 4096
    temperature: float = 0.0


class ModelRouter:
    """Routes requests to the appropriate model tier.

    The router is deterministic and based on intent metadata, not
    on runtime latency or cost (those are P3 concerns).
    """

    def __init__(
        self,
        lightweight_model: str = "",
        standard_model: str = "",
        reasoning_model: str = "",
    ) -> None:
        self._models: dict[ModelTier, str] = {
            ModelTier.LIGHTWEIGHT: lightweight_model,
            ModelTier.STANDARD: standard_model,
            ModelTier.REASONING: reasoning_model,
        }

    def route_for_intent(self, intent: str, risk_level: str = "low") -> ModelRoute:
        """Route based on intent category and risk level.

        Args:
            intent: Classified intent (from routing.intent.Intent values).
            risk_level: Tool risk level if known.

        Returns:
            A ModelRoute with the recommended tier and model.
        """
        # Simple reads → lightweight or standard
        if intent in ("account_query", "transaction_query", "beneficiary_query"):
            return ModelRoute(
                tier=ModelTier.LIGHTWEIGHT,
                model=self._models[ModelTier.LIGHTWEIGHT],
                reason="Simple read query — lightweight model sufficient",
                max_tokens=2048,
            )

        # Knowledge questions → standard
        if intent in ("policy_question", "form_assistance", "product_question"):
            return ModelRoute(
                tier=ModelTier.STANDARD,
                model=self._models[ModelTier.STANDARD],
                reason="Knowledge question — standard model for RAG",
                max_tokens=4096,
            )

        # High risk → reasoning
        if risk_level in ("high", "critical") or intent in (
            "suspicious_activity_report",
            "complex_task",
            "multi_account_task",
        ):
            return ModelRoute(
                tier=ModelTier.REASONING,
                model=self._models[ModelTier.REASONING],
                reason=f"High-risk or complex intent ({intent}) — reasoning model required",
                max_tokens=8192,
            )

        # Default → standard
        return ModelRoute(
            tier=ModelTier.STANDARD,
            model=self._models[ModelTier.STANDARD],
            reason="Default routing — standard model",
            max_tokens=4096,
        )
