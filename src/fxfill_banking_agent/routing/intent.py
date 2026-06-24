"""Intent taxonomy for banking agent requests.

Every user request is classified into one intent category. The intent
determines the execution strategy: simple reads go to direct tool workflow,
knowledge questions go to RAG, complex multi-step tasks go to Planner.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Intent(str, Enum):
    """Recognized intent categories for banking agent requests."""

    # ── Simple deterministic queries (direct tool workflow) ──────
    ACCOUNT_QUERY = "account_query"  # "What's my balance?", "Show my accounts"
    TRANSACTION_QUERY = "transaction_query"  # "Show recent transactions"
    BENEFICIARY_QUERY = "beneficiary_query"  # "Find beneficiary X"

    # ── Transfer lifecycle (state machine workflows) ─────────────
    TRANSFER_CREATE = "transfer_create"  # "Send $500 to..."
    TRANSFER_SUBMIT = "transfer_submit"  # "Submit the draft"
    TRANSFER_CANCEL = "transfer_cancel"  # "Cancel my pending transfer"
    TRANSFER_STATUS = "transfer_status"  # "Where is my transfer?"

    # ── Knowledge / policy questions (RAG) ───────────────────────
    POLICY_QUESTION = "policy_question"  # "What are the wire fees?"
    FORM_ASSISTANCE = "form_assistance"  # "How do I fill out form X?"
    PRODUCT_QUESTION = "product_question"  # "What accounts do you offer?"

    # ── High-risk / compliance ───────────────────────────────────
    SUSPICIOUS_ACTIVITY_REPORT = "suspicious_activity_report"  # "Report fraud"

    # ── Complex multi-step (Planner) ─────────────────────────────
    COMPLEX_TASK = "complex_task"  # "Send $500 to X and schedule recurring payment"
    MULTI_ACCOUNT_TASK = "multi_account_task"  # Cross-account operations

    # ── Fallback ─────────────────────────────────────────────────
    GENERAL_UNSUPPORTED = "general_unsupported"  # Out of scope / chitchat


class IntentConfidence(str, Enum):
    """Confidence level of an intent classification."""

    HIGH = "high"  # Deterministic keyword match
    MEDIUM = "medium"  # Heuristic / pattern match
    LOW = "low"  # LLM-classified, uncertain


@dataclass
class IntentResult:
    """Result of classifying a user message.

    Attributes:
        intent: The classified intent category.
        confidence: How confident the classifier is.
        reason: Human-readable explanation of the classification.
        sub_intents: Secondary intents detected (for multi-goal requests).
        suggested_tools: Tools likely needed for this intent.
    """

    intent: Intent
    confidence: IntentConfidence = IntentConfidence.HIGH
    reason: str = ""
    sub_intents: list[Intent] = field(default_factory=list)
    suggested_tools: list[str] = field(default_factory=list)

    @property
    def is_simple_read(self) -> bool:
        """True when this intent can be handled by a direct tool call."""
        return self.intent in (
            Intent.ACCOUNT_QUERY,
            Intent.TRANSACTION_QUERY,
            Intent.BENEFICIARY_QUERY,
            Intent.TRANSFER_STATUS,
        )

    @property
    def is_transfer_workflow(self) -> bool:
        """True when this intent belongs to the transfer state machine."""
        return self.intent in (
            Intent.TRANSFER_CREATE,
            Intent.TRANSFER_SUBMIT,
            Intent.TRANSFER_CANCEL,
        )

    @property
    def is_knowledge_question(self) -> bool:
        """True when this intent requires RAG-based knowledge retrieval."""
        return self.intent in (
            Intent.POLICY_QUESTION,
            Intent.FORM_ASSISTANCE,
            Intent.PRODUCT_QUESTION,
        )

    @property
    def is_complex(self) -> bool:
        """True when this intent requires the Planner–Executor."""
        return self.intent in (
            Intent.COMPLEX_TASK,
            Intent.MULTI_ACCOUNT_TASK,
        )

    @property
    def is_high_risk(self) -> bool:
        """True when this intent always requires policy validation."""
        return self.intent in (
            Intent.SUSPICIOUS_ACTIVITY_REPORT,
            Intent.TRANSFER_SUBMIT,
        )
