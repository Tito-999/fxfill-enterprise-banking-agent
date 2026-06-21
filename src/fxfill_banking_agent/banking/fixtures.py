"""Synthetic banking fixtures — deterministic test data only."""

from __future__ import annotations

from fxfill_banking_agent.banking.models import Account, Beneficiary, Transaction
from fxfill_banking_agent.banking.repository import BankingRepository


def create_test_repository() -> BankingRepository:
    """Create a repository populated with synthetic deterministic fixtures."""
    repo = BankingRepository()

    repo.load_fixtures(
        accounts=[
            Account(
                account_id="ACC-1001",
                owner_id="user-alice",
                account_type="checking",
                balance=15_000.00,
                currency="USD",
            ),
            Account(
                account_id="ACC-1002",
                owner_id="user-alice",
                account_type="savings",
                balance=50_000.00,
                currency="USD",
            ),
            Account(
                account_id="ACC-2001",
                owner_id="user-bob",
                account_type="checking",
                balance=3_500.00,
                currency="USD",
            ),
            Account(
                account_id="ACC-3001",
                owner_id="user-carol",
                account_type="checking",
                balance=250.00,
                currency="USD",
            ),
            Account(
                account_id="ACC-9001",
                owner_id="user-alice",
                account_type="checking",
                balance=0.00,
                currency="USD",
                active=False,
            ),
        ],
        beneficiaries=[
            Beneficiary(
                beneficiary_id="BEN-001",
                name="Alice's Savings",
                account_holder="Alice",
                bank_code="ABC",
                account_number="ACC-1002",
            ),
            Beneficiary(
                beneficiary_id="BEN-002",
                name="Bob's Checking",
                account_holder="Bob",
                bank_code="ABC",
                account_number="ACC-2001",
            ),
            Beneficiary(
                beneficiary_id="BEN-003",
                name="Electric Company",
                account_holder="UtilityCorp",
                bank_code="XYZ",
                account_number="UTIL-001",
            ),
            Beneficiary(
                beneficiary_id="BEN-999",
                name="Inactive Payee",
                account_holder="Unknown",
                bank_code="ZZZ",
                account_number="CLOSED",
                active=False,
            ),
        ],
    )

    # Add some seed transactions
    repo.transactions["ACC-1001"] = [
        Transaction(
            transaction_id="TXN-001",
            account_id="ACC-1001",
            amount=5000.00,
            currency="USD",
            description="Salary deposit",
            timestamp="2026-06-15T09:00:00Z",
        ),
        Transaction(
            transaction_id="TXN-002",
            account_id="ACC-1001",
            amount=-200.00,
            currency="USD",
            description="ATM withdrawal",
            timestamp="2026-06-16T14:30:00Z",
        ),
        Transaction(
            transaction_id="TXN-003",
            account_id="ACC-1001",
            amount=-1500.00,
            currency="USD",
            description="Rent payment",
            timestamp="2026-06-18T08:00:00Z",
        ),
    ]

    return repo
