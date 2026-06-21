"""Authorization gateway for the banking agent.

Implements the three-phase pipeline from ADR 004:

1. **Intent**: The agent decides what to do (LLM-produced).
2. **Authorization gate**: Deterministic check — policy decides approve/deny.
3. **Execution**: The authorized operation is dispatched.

Authorization decisions are logged for auditability.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Protocol

from fxfill_banking_agent.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


class ApprovalDecision(str, Enum):
    """Possible outcomes of an authorization check."""

    APPROVED = "approved"
    DENIED = "denied"
    PENDING = "pending"  # Requires human intervention


class OperationKind(str, Enum):
    """Categories of operations that may require authorization."""

    READ = "read"
    WRITE = "write"
    TRANSFER = "transfer"
    DELETE = "delete"
    CONFIG = "config"


@dataclass(frozen=True)
class Operation:
    """An operation that may require authorization.

    Attributes:
        kind: Category of the operation.
        name: Human-readable name (e.g. "transfer_funds").
        target: What resource is being acted upon.
        details: Additional context for the authorization decision.
    """

    kind: OperationKind
    name: str
    target: str
    details: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class AuthorizationDecision:
    """The result of an authorization check.

    Attributes:
        operation: The operation being authorized.
        decision: Approved, denied, or pending.
        reason: Human-readable explanation.
        timestamp: UTC timestamp when the decision was made.
        approver: Identifier of the human who approved, if applicable.
    """

    operation: Operation
    decision: ApprovalDecision
    reason: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    approver: str | None = None


# ---------------------------------------------------------------------------
# Authorization policy
# ---------------------------------------------------------------------------


class AuthorizationPolicy(Protocol):
    """Protocol for an authorization policy.

    The policy is deterministic — it never calls an LLM.
    """

    def authorize(self, operation: Operation) -> AuthorizationDecision:
        """Decide whether an operation is permitted.

        Args:
            operation: The proposed operation.

        Returns:
            An authorization decision with approve/deny/pending.
        """
        ...


class AutoApprovePolicy:
    """Policy that automatically approves all operations.

    Suitable for development and testing. Never use in production.
    """

    def authorize(self, operation: Operation) -> AuthorizationDecision:
        """Auto-approve every operation."""
        return AuthorizationDecision(
            operation=operation,
            decision=ApprovalDecision.APPROVED,
            reason="auto-approved (development mode)",
        )


class ReadOnlyPolicy:
    """Policy that approves reads and denies all side-effecting operations."""

    def authorize(self, operation: Operation) -> AuthorizationDecision:
        """Approve reads, deny everything else."""
        if operation.kind == OperationKind.READ:
            return AuthorizationDecision(
                operation=operation,
                decision=ApprovalDecision.APPROVED,
                reason="read operations are always permitted",
            )
        return AuthorizationDecision(
            operation=operation,
            decision=ApprovalDecision.DENIED,
            reason=f"{operation.kind.value} operations are not permitted in read-only mode",
        )


class RequireApprovalPolicy:
    """Policy that marks all non-read operations as pending human approval.

    In a real deployment, ``pending`` would trigger a notification or
    CLI prompt. In this reference implementation it blocks execution
    until an explicit approver token is provided.
    """

    def authorize(self, operation: Operation) -> AuthorizationDecision:
        """Mark writes/transfers/deletes as pending, approve reads."""
        if operation.kind == OperationKind.READ:
            return AuthorizationDecision(
                operation=operation,
                decision=ApprovalDecision.APPROVED,
                reason="read operations are always permitted",
            )
        return AuthorizationDecision(
            operation=operation,
            decision=ApprovalDecision.PENDING,
            reason="human approval required for non-read operations",
        )


# ---------------------------------------------------------------------------
# Gateway
# ---------------------------------------------------------------------------


class AuthorizationGateway:
    """Deterministic gate that enforces the authorization policy.

    Every side-effecting operation must pass through this gateway
    before execution. Decisions are logged for audit.
    """

    def __init__(
        self,
        policy: AuthorizationPolicy,
    ) -> None:
        if policy is None:
            raise RuntimeError(
                "AuthorizationGateway requires an explicit AuthorizationPolicy — refusing to fail open"
            )
        self._policy = policy
        self._decisions: list[AuthorizationDecision] = []

    @property
    def audit_trail(self) -> list[AuthorizationDecision]:
        """Return all authorization decisions made so far."""
        return list(self._decisions)

    async def authorize(self, operation: Operation) -> AuthorizationDecision:
        """Check whether an operation is authorized.

        Args:
            operation: The proposed operation.

        Returns:
            The authorization decision.
        """
        decision = self._policy.authorize(operation)
        self._decisions.append(decision)
        logger.info(
            "authorization_decision",
            operation=operation.name,
            kind=operation.kind.value,
            decision=decision.decision.value,
            reason=decision.reason,
        )
        return decision

    def clear_audit_trail(self) -> None:
        """Clear the audit trail (for testing)."""
        self._decisions.clear()
