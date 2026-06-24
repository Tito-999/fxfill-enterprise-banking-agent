"""Unit tests for banking adapter ports and sandbox adapter."""

from __future__ import annotations

import pytest

from adapters.banking_ports import (
    AccountInfo,
    TransferRequest,
    TransferResponse,
)


class TestTransferRequest:
    def test_request_creation(self) -> None:
        req = TransferRequest(
            source_account_id="ACC-1001",
            beneficiary_id="BEN-001",
            amount=500.0,
            currency="USD",
            idempotency_key="idem-1",
        )
        assert req.amount == 500.0
        assert req.currency == "USD"


class TestTransferResponse:
    def test_success_response(self) -> None:
        resp = TransferResponse(success=True, transaction_id="TXN-001", status="completed")
        assert resp.success
        assert resp.transaction_id == "TXN-001"

    def test_failure_response(self) -> None:
        resp = TransferResponse(success=False, failure_reason="Insufficient funds")
        assert not resp.success
        assert "Insufficient" in resp.failure_reason


class TestAccountInfo:
    def test_account_creation(self) -> None:
        acct = AccountInfo(
            account_id="ACC-1001",
            owner_id="user-alice",
            balance=15000.0,
            currency="USD",
            account_type="checking",
            active=True,
        )
        assert acct.active
        assert acct.balance == 15000.0


class TestSandboxAdapter:
    @pytest.mark.asyncio
    async def test_get_balance_existing(self) -> None:
        from adapters.sandbox_banking import SandboxBankingAdapter

        adapter = SandboxBankingAdapter()
        acct = await adapter.get_balance("ACC-1001", "default")
        assert acct is not None
        assert acct.owner_id == "user-alice"
        assert acct.balance == 15000.0

    @pytest.mark.asyncio
    async def test_get_balance_nonexistent(self) -> None:
        from adapters.sandbox_banking import SandboxBankingAdapter

        adapter = SandboxBankingAdapter()
        acct = await adapter.get_balance("NO-SUCH-ACCOUNT", "default")
        assert acct is None

    @pytest.mark.asyncio
    async def test_submit_transfer_success(self) -> None:
        from adapters.sandbox_banking import SandboxBankingAdapter

        adapter = SandboxBankingAdapter()
        req = TransferRequest(
            source_account_id="ACC-1001",
            beneficiary_id="BEN-001",
            amount=100.0,
            currency="USD",
        )
        resp = await adapter.submit_transfer(req, "default")
        assert resp.success
        assert resp.transaction_id.startswith("TXN-")
        assert resp.status == "completed"

    @pytest.mark.asyncio
    async def test_submit_transfer_insufficient_funds(self) -> None:
        from adapters.sandbox_banking import SandboxBankingAdapter

        adapter = SandboxBankingAdapter()
        req = TransferRequest(
            source_account_id="ACC-1001",
            beneficiary_id="BEN-001",
            amount=999_999.0,  # More than balance
            currency="USD",
        )
        resp = await adapter.submit_transfer(req, "default")
        assert not resp.success
        assert "Insufficient" in resp.failure_reason

    @pytest.mark.asyncio
    async def test_get_transfer_status(self) -> None:
        from adapters.sandbox_banking import SandboxBankingAdapter

        adapter = SandboxBankingAdapter()
        req = TransferRequest(
            source_account_id="ACC-1001",
            beneficiary_id="BEN-001",
            amount=50.0,
            currency="USD",
        )
        submit_resp = await adapter.submit_transfer(req, "default")
        status_resp = await adapter.get_transfer_status(submit_resp.transaction_id, "default")
        assert status_resp.success

    @pytest.mark.asyncio
    async def test_health(self) -> None:
        from adapters.sandbox_banking import SandboxBankingAdapter

        adapter = SandboxBankingAdapter()
        assert await adapter.health()
