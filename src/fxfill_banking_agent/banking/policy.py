"""Banking tool risk classification and validation policy.

All policies are deterministic — no LLM decisions.
"""

from __future__ import annotations

from fxfill_banking_agent.banking.models import RiskClassification

# ── Tool risk classifications ─────────────────────────────────────────

TOOL_RISK: dict[str, RiskClassification] = {
    "get_account_summary": RiskClassification.READ_ONLY,
    "get_balance": RiskClassification.READ_ONLY,
    "list_transactions": RiskClassification.READ_ONLY,
    "find_beneficiary": RiskClassification.READ_ONLY,
    "create_transfer_draft": RiskClassification.REVERSIBLE_WRITE,
    "get_transfer_status": RiskClassification.READ_ONLY,
    "cancel_transfer": RiskClassification.SIDE_EFFECTING,
    "report_suspicious_transaction": RiskClassification.SIDE_EFFECTING,
    "submit_transfer": RiskClassification.HIGH_RISK,
}


# ── Validation constants ──────────────────────────────────────────────

SUPPORTED_CURRENCIES: frozenset[str] = frozenset({"USD", "EUR", "GBP", "JPY", "CHF"})
DEFAULT_TRANSACTION_LIMIT: float = 100_000.0
TRANSFER_DRAFT_EXPIRY_MINUTES: int = 30


def requires_hitl(tool_name: str) -> bool:
    """True if this tool always requires HITL approval."""
    return TOOL_RISK.get(tool_name, RiskClassification.READ_ONLY) == RiskClassification.HIGH_RISK


def is_read_only(tool_name: str) -> bool:
    return TOOL_RISK.get(tool_name, RiskClassification.READ_ONLY) == RiskClassification.READ_ONLY
