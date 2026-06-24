"""Sandbox banking adapter — implements CoreBankingPort with synthetic data (B1).

Used for local development and contract testing. Never processes real
money or real customer data. All responses are deterministic and based
on seeded synthetic data.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from adapters.banking_ports import (
    AccountInfo,
    CoreBankingPort,
    PaymentsPort,
    TransferRequest,
    TransferResponse,
)


@dataclass
class SandboxBankingAdapter(CoreBankingPort, PaymentsPort):
    """In-memory sandbox implementation of core banking ports.

    Uses synthetic accounts and transfers for local development.
    Contract tests verify the adapter behaves correctly.
    """

    _accounts: dict[str, AccountInfo] = field(default_factory=dict)
    _transfers: dict[str, TransferResponse] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self._accounts:
            self._seed_data()

    def _seed_data(self) -> None:
        """Seed with synthetic test accounts."""
        self._accounts = {
            "ACC-1001": AccountInfo(
                account_id="ACC-1001",
                owner_id="user-alice",
                balance=15_000.00,
                currency="USD",
                account_type="checking",
                active=True,
            ),
            "ACC-1002": AccountInfo(
                account_id="ACC-1002",
                owner_id="user-bob",
                balance=8_500.00,
                currency="USD",
                account_type="savings",
                active=True,
            ),
            "ACC-1003": AccountInfo(
                account_id="ACC-1003",
                owner_id="user-carol",
                balance=25_000.00,
                currency="USD",
                account_type="checking",
                active=True,
            ),
        }

    async def get_balance(self, account_id: str, tenant_id: str) -> AccountInfo | None:
        return self._accounts.get(account_id)

    async def submit_transfer(self, request: TransferRequest, tenant_id: str) -> TransferResponse:
        import uuid

        source = self._accounts.get(request.source_account_id)
        if source is None:
            return TransferResponse(success=False, failure_reason="Source account not found")
        if source.balance < request.amount:
            return TransferResponse(success=False, failure_reason="Insufficient funds")

        txn_id = f"TXN-{uuid.uuid4().hex[:8].upper()}"
        resp = TransferResponse(
            success=True,
            transaction_id=txn_id,
            status="completed",
            upstream_reference=f"SAND-{txn_id}",
        )
        self._transfers[txn_id] = resp

        # Update balance (synthetic only!)
        self._accounts[request.source_account_id] = AccountInfo(
            account_id=source.account_id,
            owner_id=source.owner_id,
            balance=source.balance - request.amount,
            currency=source.currency,
            account_type=source.account_type,
            active=source.active,
        )

        return resp

    async def get_transfer_status(self, transaction_id: str, tenant_id: str) -> TransferResponse:
        return self._transfers.get(
            transaction_id,
            TransferResponse(success=False, failure_reason="Transaction not found"),
        )

    async def initiate_payment(self, request: TransferRequest, tenant_id: str) -> TransferResponse:
        return await self.submit_transfer(request, tenant_id)

    async def check_payment_status(self, payment_id: str, tenant_id: str) -> TransferResponse:
        return await self.get_transfer_status(payment_id, tenant_id)

    async def health(self) -> bool:
        return True
