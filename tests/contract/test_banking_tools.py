"""Contract tests for synthetic banking tools."""

from __future__ import annotations

import json

import pytest

from fxfill_banking_agent.banking.fixtures import create_test_repository
from fxfill_banking_agent.banking.tools import BankingTools


@pytest.fixture
def tools() -> BankingTools:
    return BankingTools(create_test_repository())


class TestReadOnlyTools:
    def test_get_balance(self, tools: BankingTools) -> None:
        result, error = tools.execute(
            "get_balance", {"account_id": "ACC-1001", "user_id": "user-alice"}
        )
        assert error is None
        data = json.loads(result)
        assert data["balance"] == 15000.0

    def test_get_account_summary(self, tools: BankingTools) -> None:
        result, error = tools.execute(
            "get_account_summary", {"account_id": "ACC-1001", "user_id": "user-alice"}
        )
        assert error is None
        data = json.loads(result)
        assert data["owner_id"] == "user-alice"

    def test_list_transactions(self, tools: BankingTools) -> None:
        result, error = tools.execute(
            "list_transactions", {"account_id": "ACC-1001", "user_id": "user-alice"}
        )
        assert error is None
        data = json.loads(result)
        assert len(data) >= 1

    def test_ownership_violation(self, tools: BankingTools) -> None:
        result, error = tools.execute(
            "get_balance", {"account_id": "ACC-1001", "user_id": "user-bob"}
        )
        assert error is not None
        assert "access denied" in error.lower() or "not found" in error.lower()

    def test_find_beneficiary(self, tools: BankingTools) -> None:
        result, error = tools.execute("find_beneficiary", {"beneficiary_id": "BEN-001"})
        assert error is None


class TestTransferDraft:
    def test_create_draft(self, tools: BankingTools) -> None:
        result, error = tools.execute(
            "create_transfer_draft",
            {
                "source_account_id": "ACC-1001",
                "beneficiary_id": "BEN-002",
                "amount": 500.0,
                "currency": "USD",
                "user_id": "user-alice",
                "idempotency_key": "idem-1",
            },
        )
        assert error is None
        data = json.loads(result)
        assert data["status"] == "DRAFT"

    def test_invalid_amount(self, tools: BankingTools) -> None:
        result, error = tools.execute(
            "create_transfer_draft",
            {
                "source_account_id": "ACC-1001",
                "beneficiary_id": "BEN-002",
                "amount": -100.0,
                "currency": "USD",
                "user_id": "user-alice",
                "idempotency_key": "idem-neg",
            },
        )
        assert error is not None

    def test_insufficient_funds(self, tools: BankingTools) -> None:
        result, error = tools.execute(
            "create_transfer_draft",
            {
                "source_account_id": "ACC-1001",
                "beneficiary_id": "BEN-002",
                "amount": 999999.0,
                "currency": "USD",
                "user_id": "user-alice",
                "idempotency_key": "idem-big",
            },
        )
        assert error is not None

    def test_submit_transfer(self, tools: BankingTools) -> None:
        draft_result, _ = tools.execute(
            "create_transfer_draft",
            {
                "source_account_id": "ACC-3001",
                "beneficiary_id": "BEN-003",
                "amount": 100.0,
                "currency": "USD",
                "user_id": "user-carol",
                "idempotency_key": "idem-2",
            },
        )
        draft_id = json.loads(draft_result)["draft_id"]
        result, error = tools.execute(
            "submit_transfer", {"draft_id": draft_id, "user_id": "user-carol"}
        )
        assert error is None
        data = json.loads(result)
        assert data["status"] == "COMPLETED"

    def test_cancel_transfer(self, tools: BankingTools) -> None:
        draft_result, _ = tools.execute(
            "create_transfer_draft",
            {
                "source_account_id": "ACC-3001",
                "beneficiary_id": "BEN-003",
                "amount": 50.0,
                "currency": "USD",
                "user_id": "user-carol",
                "idempotency_key": "idem-3",
            },
        )
        draft_id = json.loads(draft_result)["draft_id"]
        result, error = tools.execute(
            "cancel_transfer", {"draft_id": draft_id, "user_id": "user-carol"}
        )
        assert error is None
