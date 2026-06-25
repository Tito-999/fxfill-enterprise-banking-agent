"""Stage 1.3/1.5: RBAC + ABAC + tenant isolation tests."""

from __future__ import annotations

import pytest

from fxfill_banking_agent.security.authorization import (
    CompositePolicy,
    RBACPolicy,
    ResourceAttributes,
    TenantScopedPolicy,
)
from fxfill_banking_agent.security.context import TrustedRequestContext


class TestTenantScopedPolicy:
    """Cross-tenant access must be denied."""

    @pytest.mark.asyncio
    async def test_same_tenant_allowed(self) -> None:
        policy = TenantScopedPolicy()
        ctx = TrustedRequestContext(subject_id="alice", tenant_id="t1")
        resource = ResourceAttributes(resource_type="account", resource_id="ACC-1", tenant_id="t1")
        decision = await policy.authorize(ctx, resource, "read_account")
        assert decision.allowed

    @pytest.mark.asyncio
    async def test_cross_tenant_denied(self) -> None:
        policy = TenantScopedPolicy()
        ctx = TrustedRequestContext(subject_id="alice", tenant_id="t1")
        resource = ResourceAttributes(resource_type="account", resource_id="ACC-2", tenant_id="t2")
        decision = await policy.authorize(ctx, resource, "read_account")
        assert not decision.allowed
        assert decision.error_code == "CROSS_TENANT_DENIED"

    @pytest.mark.asyncio
    async def test_account_ownership_enforced(self) -> None:
        policy = TenantScopedPolicy()
        ctx = TrustedRequestContext(subject_id="alice", tenant_id="t1")
        resource = ResourceAttributes(
            resource_type="account",
            resource_id="ACC-2",
            tenant_id="t1",
            owner_subject_id="bob",
        )
        decision = await policy.authorize(ctx, resource, "read_account")
        assert not decision.allowed
        assert decision.error_code == "ACCOUNT_ACCESS_DENIED"

    @pytest.mark.asyncio
    async def test_banking_officer_can_access_other_accounts(self) -> None:
        policy = TenantScopedPolicy()
        ctx = TrustedRequestContext(
            subject_id="officer",
            tenant_id="t1",
            roles=frozenset({"banking_officer"}),
        )
        resource = ResourceAttributes(
            resource_type="account",
            resource_id="ACC-2",
            tenant_id="t1",
            owner_subject_id="bob",
        )
        decision = await policy.authorize(ctx, resource, "read_account")
        assert decision.allowed


class TestRBACPolicy:
    """Role-based access control."""

    @pytest.mark.asyncio
    async def test_customer_cannot_approve(self) -> None:
        policy = RBACPolicy()
        ctx = TrustedRequestContext(
            subject_id="alice",
            tenant_id="t1",
            roles=frozenset({"customer"}),
        )
        resource = ResourceAttributes(resource_type="transfer")
        decision = await policy.authorize(ctx, resource, "approve_critical")
        assert not decision.allowed
        assert decision.error_code == "INSUFFICIENT_PERMISSION"

    @pytest.mark.asyncio
    async def test_approver_can_approve(self) -> None:
        policy = RBACPolicy()
        ctx = TrustedRequestContext(
            subject_id="officer",
            tenant_id="t1",
            roles=frozenset({"approver"}),
        )
        resource = ResourceAttributes(resource_type="transfer")
        decision = await policy.authorize(ctx, resource, "approve_critical")
        assert decision.allowed

    @pytest.mark.asyncio
    async def test_no_roles_denied(self) -> None:
        policy = RBACPolicy()
        ctx = TrustedRequestContext(subject_id="alice", tenant_id="t1")
        resource = ResourceAttributes(resource_type="account")
        decision = await policy.authorize(ctx, resource, "read_account")
        assert not decision.allowed


class TestCompositePolicy:
    """Multiple policies — all must pass."""

    @pytest.mark.asyncio
    async def test_all_must_pass(self) -> None:
        composite = CompositePolicy([TenantScopedPolicy(), RBACPolicy()])
        ctx = TrustedRequestContext(
            subject_id="officer",
            tenant_id="t1",
            roles=frozenset({"banking_officer"}),
        )
        resource = ResourceAttributes(
            resource_type="account",
            resource_id="ACC-2",
            tenant_id="t1",
            owner_subject_id="bob",
        )
        decision = await composite.authorize(ctx, resource, "read_account")
        assert decision.allowed

    @pytest.mark.asyncio
    async def test_first_fail_blocks(self) -> None:
        composite = CompositePolicy([TenantScopedPolicy(), RBACPolicy()])
        ctx = TrustedRequestContext(subject_id="alice", tenant_id="t1")
        resource = ResourceAttributes(tenant_id="t2")
        decision = await composite.authorize(ctx, resource, "read_account")
        assert not decision.allowed
        assert decision.error_code == "CROSS_TENANT_DENIED"
