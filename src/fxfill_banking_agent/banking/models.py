"""Synthetic banking data models — no real customer data."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class RiskClassification(str, Enum):
    READ_ONLY = "READ_ONLY"
    REVERSIBLE_WRITE = "REVERSIBLE_WRITE"
    SIDE_EFFECTING = "SIDE_EFFECTING"
    HIGH_RISK = "HIGH_RISK"


class TransferStatus(str, Enum):
    DRAFT = "DRAFT"
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


@dataclass
class Account:
    account_id: str
    owner_id: str
    account_type: str = "checking"
    balance: float = 0.0
    currency: str = "USD"
    active: bool = True


@dataclass
class Beneficiary:
    beneficiary_id: str
    name: str
    account_holder: str
    bank_code: str = ""
    account_number: str = ""
    active: bool = True


@dataclass
class Transaction:
    transaction_id: str
    account_id: str
    amount: float
    currency: str = "USD"
    description: str = ""
    timestamp: str = ""


@dataclass
class TransferDraft:
    draft_id: str
    source_account_id: str
    beneficiary_id: str
    amount: float
    currency: str = "USD"
    description: str = ""
    status: TransferStatus = TransferStatus.DRAFT
    idempotency_key: str = ""
    created_at: str = ""
    expires_at: str = ""


@dataclass
class AccountSummary:
    account: Account
    recent_transactions: list[Transaction] = field(default_factory=list)
    beneficiary_count: int = 0
