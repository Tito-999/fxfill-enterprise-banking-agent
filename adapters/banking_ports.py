"""Core banking adapter ports (P2-03).

These are typed interfaces that the agent runtime calls. Concrete
implementations connect to real core banking systems, sandbox
environments, or synthetic repositories.

All adapters must implement:
- Timeout and retry with circuit breaker
- Request signing / mTLS
- Idempotency key passthrough
- Upstream correlation ID
- Response schema validation
- PII redaction in logs
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class TransferRequest:
    """A transfer request to the core banking system."""

    source_account_id: str
    beneficiary_id: str
    amount: float
    currency: str
    reference: str = ""
    idempotency_key: str = ""
    correlation_id: str = ""


@dataclass(frozen=True)
class TransferResponse:
    """Response from a core banking transfer."""

    success: bool
    transaction_id: str = ""
    status: str = ""  # "completed", "pending", "failed", "unknown"
    failure_reason: str = ""
    upstream_reference: str = ""


@dataclass(frozen=True)
class AccountInfo:
    """Account information from core banking."""

    account_id: str
    owner_id: str
    balance: float = 0.0
    currency: str = "USD"
    account_type: str = ""
    active: bool = True


class CoreBankingPort(Protocol):
    """Port for core banking operations.

    Implementations connect to real banking APIs. The sandbox adapter
    uses synthetic data for local development.
    """

    async def get_balance(self, account_id: str, tenant_id: str) -> AccountInfo | None:
        """Get account balance and metadata."""
        ...

    async def submit_transfer(self, request: TransferRequest, tenant_id: str) -> TransferResponse:
        """Submit a transfer for execution."""
        ...

    async def get_transfer_status(self, transaction_id: str, tenant_id: str) -> TransferResponse:
        """Check the status of a submitted transfer."""
        ...


class PaymentsPort(Protocol):
    """Port for payment processing (wire, ACH, etc.)."""

    async def initiate_payment(self, request: TransferRequest, tenant_id: str) -> TransferResponse:
        """Initiate a payment through the payments rail."""
        ...

    async def check_payment_status(self, payment_id: str, tenant_id: str) -> TransferResponse:
        """Check payment status."""
        ...


class AMLPort(Protocol):
    """Port for Anti-Money Laundering checks."""

    async def screen_transaction(
        self,
        amount: float,
        source_account_id: str,
        beneficiary_id: str,
        correlation_id: str,
    ) -> dict[str, Any]:
        """Screen a transaction for AML flags."""
        ...


class SanctionsPort(Protocol):
    """Port for sanctions screening."""

    async def screen_beneficiary(
        self, beneficiary_id: str, beneficiary_name: str, correlation_id: str
    ) -> dict[str, Any]:
        """Screen a beneficiary against sanctions lists."""
        ...
