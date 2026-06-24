"""Data security and privacy (P2-04).

Defines data classification levels, field-level policies for logging/
prompt/storage, encryption interfaces, and retention/deletion rules.

Never stores raw tokens, full account numbers, or PII in logs or audit.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class DataClassification(str, Enum):
    """Data sensitivity levels."""

    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    FINANCIAL_CONFIDENTIAL = "financial_confidential"
    RESTRICTED_PII = "restricted_pii"
    SECRET = "secret"


@dataclass(frozen=True)
class FieldPolicy:
    """Policy for a single data field.

    Attributes:
        field_name: Name of the field.
        classification: Data sensitivity level.
        can_enter_prompt: Whether this field can be sent to the LLM.
        can_enter_log: Whether this field can appear in logs.
        can_enter_vector_store: Whether this field enters RAG indices.
        can_persist_long_term: Whether this field can be stored beyond the session.
        retention_days: How long to retain (0 = session only).
        redaction_rule: How to redact ("full", "last4", "hash", "none").
    """

    field_name: str
    classification: DataClassification = DataClassification.INTERNAL
    can_enter_prompt: bool = True
    can_enter_log: bool = False
    can_enter_vector_store: bool = False
    can_persist_long_term: bool = False
    retention_days: int = 0
    redaction_rule: str = "full"


# ── Default field policies ──────────────────────────────────────────

DEFAULT_FIELD_POLICIES: dict[str, FieldPolicy] = {
    "user_id": FieldPolicy(
        "user_id",
        classification=DataClassification.INTERNAL,
        can_enter_prompt=False,
        can_enter_log=True,
    ),
    "account_id": FieldPolicy(
        "account_id",
        classification=DataClassification.CONFIDENTIAL,
        can_enter_prompt=True,
        can_enter_log=False,
        redaction_rule="last4",
    ),
    "full_account_number": FieldPolicy(
        "full_account_number",
        classification=DataClassification.RESTRICTED_PII,
        can_enter_prompt=False,
        can_enter_log=False,
    ),
    "balance": FieldPolicy(
        "balance",
        classification=DataClassification.FINANCIAL_CONFIDENTIAL,
        can_enter_prompt=True,
        can_enter_log=False,
    ),
    "transaction_id": FieldPolicy(
        "transaction_id",
        classification=DataClassification.CONFIDENTIAL,
        can_enter_prompt=True,
        can_enter_log=True,
    ),
    "api_key": FieldPolicy(
        "api_key",
        classification=DataClassification.SECRET,
        can_enter_prompt=False,
        can_enter_log=False,
        redaction_rule="full",
    ),
    "token": FieldPolicy(
        "token",
        classification=DataClassification.SECRET,
        can_enter_prompt=False,
        can_enter_log=False,
        redaction_rule="full",
    ),
}


def get_field_policy(field_name: str) -> FieldPolicy:
    """Return the policy for a field, or a safe default."""
    return DEFAULT_FIELD_POLICIES.get(
        field_name,
        FieldPolicy(field_name, classification=DataClassification.INTERNAL),
    )


# ── Retention and deletion ──────────────────────────────────────────


@dataclass
class RetentionPolicy:
    """Data retention and deletion rules.

    Attributes:
        data_category: What kind of data.
        retention_days: How long to keep it.
        auto_delete: Whether deletion is automatic.
        legal_hold_supported: Whether legal hold can override retention.
        exportable: Whether users can export this data.
    """

    data_category: str
    retention_days: int = 90
    auto_delete: bool = True
    legal_hold_supported: bool = False
    exportable: bool = True


DEFAULT_RETENTION_POLICIES: list[RetentionPolicy] = [
    RetentionPolicy("conversation_history", retention_days=90),
    RetentionPolicy("audit_events", retention_days=2555),  # 7 years
    RetentionPolicy("approval_grants", retention_days=365),
    RetentionPolicy("idempotency_records", retention_days=90),
    RetentionPolicy("user_preferences", retention_days=365, exportable=True),
    RetentionPolicy("rag_indices", retention_days=0, auto_delete=False),
]
