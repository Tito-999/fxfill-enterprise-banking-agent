"""In-memory synthetic banking data repository — no real accounts."""

from __future__ import annotations

import copy
import uuid
from datetime import datetime, timedelta, timezone

from fxfill_banking_agent.banking.models import (
    Account,
    AccountSummary,
    Beneficiary,
    Transaction,
    TransferDraft,
    TransferStatus,
)
from fxfill_banking_agent.banking.policy import (
    DEFAULT_TRANSACTION_LIMIT,
    TRANSFER_DRAFT_EXPIRY_MINUTES,
)


class BankingRepository:
    """In-memory synthetic banking store with deterministic fixtures."""

    def __init__(self) -> None:
        self.accounts: dict[str, Account] = {}
        self.beneficiaries: dict[str, Beneficiary] = {}
        self.transactions: dict[str, list[Transaction]] = {}
        self.transfer_drafts: dict[str, TransferDraft] = {}
        self._completed_transfers: set[str] = set()  # idempotency keys

    # ── Account operations ────────────────────────────────────────

    def load_fixtures(self, accounts: list[Account], beneficiaries: list[Beneficiary]) -> None:
        for a in accounts:
            self.accounts[a.account_id] = copy.deepcopy(a)
            self.transactions.setdefault(a.account_id, [])
        for b in beneficiaries:
            self.beneficiaries[b.beneficiary_id] = copy.deepcopy(b)

    def get_account(self, account_id: str) -> Account | None:
        return self.accounts.get(account_id)

    def owner_of(self, account_id: str, user_id: str) -> bool:
        acc = self.accounts.get(account_id)
        return acc is not None and acc.owner_id == user_id

    def get_balance(self, account_id: str, user_id: str) -> float | None:
        acc = self.accounts.get(account_id)
        if acc is None or acc.owner_id != user_id:
            return None
        return acc.balance

    def get_summary(self, account_id: str, user_id: str) -> AccountSummary | None:
        acc = self.accounts.get(account_id)
        if acc is None or acc.owner_id != user_id:
            return None
        txs = self.transactions.get(account_id, [])
        return AccountSummary(
            account=copy.deepcopy(acc),
            recent_transactions=list(txs[-10:]),
            beneficiary_count=len(self.beneficiaries),
        )

    def list_transactions(
        self, account_id: str, user_id: str, limit: int = 20
    ) -> list[Transaction] | None:
        if not self.owner_of(account_id, user_id):
            return None
        txs = self.transactions.get(account_id, [])
        return list(txs[-limit:])

    # ── Beneficiary operations ────────────────────────────────────

    def get_beneficiary(self, beneficiary_id: str) -> Beneficiary | None:
        return self.beneficiaries.get(beneficiary_id)

    # ── Transfer operations ───────────────────────────────────────

    def create_transfer_draft(
        self,
        source_account_id: str,
        beneficiary_id: str,
        amount: float,
        currency: str,
        user_id: str,
        idempotency_key: str,
        description: str = "",
    ) -> tuple[TransferDraft | None, str | None]:
        """Validate and create a transfer draft. Returns (draft, error)."""
        # Validate source
        acc = self.accounts.get(source_account_id)
        if acc is None:
            return None, f"Account not found: {source_account_id}"
        if not acc.active:
            return None, f"Account inactive: {source_account_id}"
        if acc.owner_id != user_id:
            return None, f"User {user_id} does not own account {source_account_id}"

        # Validate beneficiary
        ben = self.beneficiaries.get(beneficiary_id)
        if ben is None:
            return None, f"Beneficiary not found: {beneficiary_id}"
        if not ben.active:
            return None, f"Beneficiary inactive: {beneficiary_id}"

        # Validate amount
        if amount <= 0:
            return None, "Amount must be positive"
        if amount > DEFAULT_TRANSACTION_LIMIT:
            return None, f"Amount exceeds limit of {DEFAULT_TRANSACTION_LIMIT}"
        if currency not in ("USD", "EUR", "GBP", "JPY", "CHF"):
            return None, f"Unsupported currency: {currency}"

        # Check balance
        if acc.balance < amount:
            return None, f"Insufficient funds: balance {acc.balance} < {amount}"

        # Check idempotency
        if idempotency_key in self._completed_transfers:
            return None, "Transfer already completed (idempotency key)"

        now = datetime.now(timezone.utc)
        draft = TransferDraft(
            draft_id=str(uuid.uuid4()),
            source_account_id=source_account_id,
            beneficiary_id=beneficiary_id,
            amount=amount,
            currency=currency,
            description=description,
            status=TransferStatus.DRAFT,
            idempotency_key=idempotency_key,
            created_at=now.isoformat(),
            expires_at=(now + timedelta(minutes=TRANSFER_DRAFT_EXPIRY_MINUTES)).isoformat(),
        )
        self.transfer_drafts[draft.draft_id] = draft
        return draft, None

    def submit_transfer(
        self, draft_id: str, user_id: str
    ) -> tuple[TransferDraft | None, str | None]:
        draft = self.transfer_drafts.get(draft_id)
        if draft is None:
            return None, f"Draft not found: {draft_id}"
        if draft.status != TransferStatus.DRAFT:
            return None, f"Draft already {draft.status.value}"
        if not self.owner_of(draft.source_account_id, user_id):
            return None, "Ownership violation"

        # Check expiry
        if draft.expires_at:
            expires = datetime.fromisoformat(draft.expires_at)
            if datetime.now(timezone.utc) > expires:
                draft.status = TransferStatus.FAILED
                return None, "Draft expired"

        # Check idempotency
        if draft.idempotency_key and draft.idempotency_key in self._completed_transfers:
            return None, "Transfer already completed"

        # Execute
        acc = self.accounts[draft.source_account_id]
        if acc.balance < draft.amount:
            return None, "Insufficient funds"

        acc.balance -= draft.amount
        draft.status = TransferStatus.COMPLETED

        # Record transaction
        txn = Transaction(
            transaction_id=str(uuid.uuid4()),
            account_id=draft.source_account_id,
            amount=-draft.amount,
            currency=draft.currency,
            description=draft.description or f"Transfer to {draft.beneficiary_id}",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        self.transactions.setdefault(draft.source_account_id, []).append(txn)

        if draft.idempotency_key:
            self._completed_transfers.add(draft.idempotency_key)

        return draft, None

    def cancel_transfer(self, draft_id: str, user_id: str) -> tuple[bool, str | None]:
        draft = self.transfer_drafts.get(draft_id)
        if draft is None:
            return False, f"Draft not found: {draft_id}"
        if draft.status not in (TransferStatus.DRAFT, TransferStatus.PENDING):
            return False, f"Cannot cancel: draft is {draft.status.value}"
        if not self.owner_of(draft.source_account_id, user_id):
            return False, "Ownership violation"
        draft.status = TransferStatus.CANCELLED
        return True, None

    def get_transfer_status(self, draft_id: str) -> TransferDraft | None:
        return self.transfer_drafts.get(draft_id)

    def is_idempotency_key_used(self, key: str) -> bool:
        return key in self._completed_transfers
