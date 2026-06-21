"""Tests for authorization gateway."""

from __future__ import annotations

import pytest

from fxfill_banking_agent.auth import (
    ApprovalDecision,
    AuthorizationGateway,
    AutoApprovePolicy,
    Operation,
    OperationKind,
    ReadOnlyPolicy,
    RequireApprovalPolicy,
)


class TestAutoApprovePolicy:
    def test_approves_read(self) -> None:
        policy = AutoApprovePolicy()
        op = Operation(kind=OperationKind.READ, name="get_balance", target="account:123")
        decision = policy.authorize(op)
        assert decision.decision == ApprovalDecision.APPROVED

    def test_approves_write(self) -> None:
        policy = AutoApprovePolicy()
        op = Operation(kind=OperationKind.WRITE, name="update_profile", target="user:1")
        decision = policy.authorize(op)
        assert decision.decision == ApprovalDecision.APPROVED

    def test_approves_transfer(self) -> None:
        policy = AutoApprovePolicy()
        op = Operation(kind=OperationKind.TRANSFER, name="transfer_funds", target="txn:42")
        decision = policy.authorize(op)
        assert decision.decision == ApprovalDecision.APPROVED


class TestReadOnlyPolicy:
    def test_approves_read(self) -> None:
        policy = ReadOnlyPolicy()
        op = Operation(kind=OperationKind.READ, name="get_balance", target="account:1")
        decision = policy.authorize(op)
        assert decision.decision == ApprovalDecision.APPROVED

    def test_denies_write(self) -> None:
        policy = ReadOnlyPolicy()
        op = Operation(kind=OperationKind.WRITE, name="update", target="account:1")
        decision = policy.authorize(op)
        assert decision.decision == ApprovalDecision.DENIED

    def test_denies_transfer(self) -> None:
        policy = ReadOnlyPolicy()
        op = Operation(kind=OperationKind.TRANSFER, name="wire", target="account:1")
        decision = policy.authorize(op)
        assert decision.decision == ApprovalDecision.DENIED

    def test_denies_delete(self) -> None:
        policy = ReadOnlyPolicy()
        op = Operation(kind=OperationKind.DELETE, name="purge", target="account:1")
        decision = policy.authorize(op)
        assert decision.decision == ApprovalDecision.DENIED


class TestRequireApprovalPolicy:
    def test_approves_read(self) -> None:
        policy = RequireApprovalPolicy()
        op = Operation(kind=OperationKind.READ, name="lookup", target="account:1")
        decision = policy.authorize(op)
        assert decision.decision == ApprovalDecision.APPROVED

    def test_pends_write(self) -> None:
        policy = RequireApprovalPolicy()
        op = Operation(kind=OperationKind.WRITE, name="update", target="account:1")
        decision = policy.authorize(op)
        assert decision.decision == ApprovalDecision.PENDING

    def test_pends_transfer(self) -> None:
        policy = RequireApprovalPolicy()
        op = Operation(kind=OperationKind.TRANSFER, name="wire", target="account:1")
        decision = policy.authorize(op)
        assert decision.decision == ApprovalDecision.PENDING


class TestAuthorizationGateway:
    @pytest.mark.asyncio
    async def test_delegates_to_policy(self) -> None:
        gateway = AuthorizationGateway(policy=AutoApprovePolicy())
        op = Operation(kind=OperationKind.WRITE, name="test", target="x")
        decision = await gateway.authorize(op)
        assert decision.decision == ApprovalDecision.APPROVED

    @pytest.mark.asyncio
    async def test_records_audit_trail(self) -> None:
        gateway = AuthorizationGateway(policy=AutoApprovePolicy())
        await gateway.authorize(Operation(OperationKind.READ, "a", "x"))
        await gateway.authorize(Operation(OperationKind.WRITE, "b", "y"))

        trail = gateway.audit_trail
        assert len(trail) == 2
        assert trail[0].operation.name == "a"
        assert trail[1].operation.name == "b"

    @pytest.mark.asyncio
    async def test_clear_audit_trail(self) -> None:
        gateway = AuthorizationGateway(policy=AutoApprovePolicy())
        await gateway.authorize(Operation(OperationKind.READ, "a", "x"))
        assert len(gateway.audit_trail) == 1
        gateway.clear_audit_trail()
        assert len(gateway.audit_trail) == 0

    @pytest.mark.asyncio
    async def test_default_policy_is_auto_approve(self) -> None:
        gateway = AuthorizationGateway()
        op = Operation(OperationKind.DELETE, "dangerous", "data")
        decision = await gateway.authorize(op)
        assert decision.decision == ApprovalDecision.APPROVED

    @pytest.mark.asyncio
    async def test_denied_operations_recorded(self) -> None:
        gateway = AuthorizationGateway(policy=ReadOnlyPolicy())
        op = Operation(OperationKind.WRITE, "blocked", "x")
        decision = await gateway.authorize(op)
        assert decision.decision == ApprovalDecision.DENIED
        assert len(gateway.audit_trail) == 1

    @pytest.mark.asyncio
    async def test_operation_details_preserved(self) -> None:
        gateway = AuthorizationGateway(policy=ReadOnlyPolicy())
        op = Operation(
            kind=OperationKind.TRANSFER,
            name="send_money",
            target="from:alice,to:bob",
            details={"amount": 100, "currency": "USD"},
        )
        decision = await gateway.authorize(op)
        assert decision.operation.details == {"amount": 100, "currency": "USD"}
