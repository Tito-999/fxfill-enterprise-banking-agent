"""RBAC + ABAC authorization policies (Stage 1.3).

Multi-tenant, role-based, attribute-based authorization.
All resource queries MUST include tenant_id scope.
Identity NEVER comes from LLM, prompt, or HTTP body.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from fxfill_banking_agent.security.context import TrustedRequestContext


@dataclass(frozen=True)
class ResourceAttributes:
    """Attributes of the resource being accessed."""

    resource_type: str = ""
    resource_id: str = ""
    tenant_id: str = ""
    owner_subject_id: str = ""
    risk_level: str = "low"
    side_effect: bool = False


@dataclass(frozen=True)
class AuthzDecision:
    """Result of an authorization check."""

    allowed: bool
    reason: str = ""
    error_code: str = ""

    @staticmethod
    def deny(reason: str, error_code: str = "ACCESS_DENIED") -> AuthzDecision:
        return AuthzDecision(allowed=False, reason=reason, error_code=error_code)

    @staticmethod
    def allow(reason: str = "") -> AuthzDecision:
        return AuthzDecision(allowed=True, reason=reason)


class AuthorizationPolicy(Protocol):
    """Protocol for authorization policy decisions."""

    async def authorize(
        self,
        context: TrustedRequestContext,
        resource: ResourceAttributes,
        action: str,
    ) -> AuthzDecision: ...


class TenantScopedPolicy:
    """Enforces tenant-scoped access to all resources.

    Every authorization check verifies the user's tenant matches
    the resource's tenant. Cross-tenant access is always denied.
    """

    async def authorize(
        self,
        context: TrustedRequestContext,
        resource: ResourceAttributes,
        action: str,
    ) -> AuthzDecision:
        # ── Tenant isolation ────────────────────────────────────
        if resource.tenant_id and context.tenant_id != resource.tenant_id:
            return AuthzDecision.deny("Cross-tenant access denied", "CROSS_TENANT_DENIED")

        # ── Account ownership ────────────────────────────────────
        if (
            resource.resource_type == "account"
            and resource.owner_subject_id
            and context.subject_id != resource.owner_subject_id
            and "banking_officer" not in context.roles
        ):
            return AuthzDecision.deny("Account access denied", "ACCOUNT_ACCESS_DENIED")

        # ── Role checks ──────────────────────────────────────────
        if resource.risk_level == "critical" and "approver" not in context.roles:
            return AuthzDecision.deny(
                "Critical operation requires approver role", "INSUFFICIENT_ROLE"
            )

        return AuthzDecision.allow(f"Access granted to {context.subject_id}")


class RBACPolicy:
    """Role-based access control using the IAM role/permission model."""

    def __init__(self) -> None:
        from fxfill_banking_agent.iam import Permission, Role, has_permission

        self._has_permission = has_permission
        self.Permission = Permission
        self.Role = Role

    async def authorize(
        self,
        context: TrustedRequestContext,
        resource: ResourceAttributes,
        action: str,
    ) -> AuthzDecision:
        valid_values = {r.value for r in self.Role}
        roles = {self.Role(r) for r in context.roles if r in valid_values}
        if not roles:
            return AuthzDecision.deny("No valid roles", "NO_ROLES")

        perm = _action_to_permission(action, resource)
        if perm is None:
            return AuthzDecision.deny(f"Unknown action: {action}", "UNKNOWN_ACTION")

        if self._has_permission(frozenset(roles), perm):
            return AuthzDecision.allow(f"Permission {perm.value} granted")
        return AuthzDecision.deny(f"Missing permission: {perm.value}", "INSUFFICIENT_PERMISSION")


def _action_to_permission(action: str, resource: ResourceAttributes) -> Any | None:
    """Map an action + resource to a Permission."""
    from fxfill_banking_agent.iam import Permission

    mapping: dict[str, Permission] = {
        "read_account": Permission.ACCOUNT_READ,
        "read_own_account": Permission.ACCOUNT_READ_OWN,
        "create_transfer": Permission.TRANSFER_CREATE,
        "submit_transfer": Permission.TRANSFER_SUBMIT,
        "cancel_transfer": Permission.TRANSFER_CANCEL,
        "read_transfer": Permission.TRANSFER_READ,
        "read_beneficiary": Permission.BENEFICIARY_READ,
        "audit_read": Permission.AUDIT_READ,
        "report_suspicious": Permission.REPORT_SUSPICIOUS,
        "approve_low_risk": Permission.APPROVE_LOW_RISK,
        "approve_high_risk": Permission.APPROVE_HIGH_RISK,
        "approve_critical": Permission.APPROVE_CRITICAL,
    }
    return mapping.get(action)


# ── Composite policy ──────────────────────────────────────────────────


class CompositePolicy:
    """Runs multiple policies in order — all must pass."""

    def __init__(self, policies: list[AuthorizationPolicy]) -> None:
        self._policies = policies

    async def authorize(
        self,
        context: TrustedRequestContext,
        resource: ResourceAttributes,
        action: str,
    ) -> AuthzDecision:
        for policy in self._policies:
            decision = await policy.authorize(context, resource, action)
            if not decision.allowed:
                return decision
        return AuthzDecision.allow("All policies passed")
