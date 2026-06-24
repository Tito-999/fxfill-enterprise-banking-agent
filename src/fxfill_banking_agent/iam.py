"""IAM — Identity and Access Management (P2-02).

Enterprise authentication and authorization models:
- OIDC/JWT verification
- RBAC (Role-Based Access Control)
- ABAC (Attribute-Based Access Control)
- Maker-Checker (dual approval for critical operations)
- Multi-tenant isolation

All identity fields come from verified tokens/context, never from
client-controlled request body fields.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Role(str, Enum):
    """Predefined roles for RBAC."""

    CUSTOMER = "customer"
    BANKING_OFFICER = "banking_officer"
    APPROVER = "approver"
    COMPLIANCE_OFFICER = "compliance_officer"
    ADMIN = "admin"
    AUDITOR = "auditor"
    SYSTEM = "system"


class Permission(str, Enum):
    """Granular permissions for ABAC policies."""

    # Account access
    ACCOUNT_READ = "account:read"
    ACCOUNT_READ_OWN = "account:read_own"

    # Transfer operations
    TRANSFER_CREATE = "transfer:create"
    TRANSFER_SUBMIT = "transfer:submit"
    TRANSFER_CANCEL = "transfer:cancel"
    TRANSFER_READ = "transfer:read"

    # Beneficiary
    BENEFICIARY_READ = "beneficiary:read"

    # Admin / compliance
    AUDIT_READ = "audit:read"
    USER_MANAGE = "user:manage"
    REPORT_SUSPICIOUS = "report:suspicious"

    # Approval
    APPROVE_LOW_RISK = "approve:low_risk"
    APPROVE_HIGH_RISK = "approve:high_risk"
    APPROVE_CRITICAL = "approve:critical"


# ── Role → Permission mapping ──────────────────────────────────────

ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.CUSTOMER: frozenset(
        {
            Permission.ACCOUNT_READ_OWN,
            Permission.TRANSFER_CREATE,
            Permission.TRANSFER_CANCEL,
            Permission.TRANSFER_READ,
            Permission.BENEFICIARY_READ,
            Permission.REPORT_SUSPICIOUS,
        }
    ),
    Role.BANKING_OFFICER: frozenset(
        {
            Permission.ACCOUNT_READ,
            Permission.TRANSFER_CREATE,
            Permission.TRANSFER_SUBMIT,
            Permission.TRANSFER_CANCEL,
            Permission.TRANSFER_READ,
            Permission.BENEFICIARY_READ,
            Permission.APPROVE_LOW_RISK,
            Permission.REPORT_SUSPICIOUS,
        }
    ),
    Role.APPROVER: frozenset(
        {
            Permission.ACCOUNT_READ,
            Permission.TRANSFER_READ,
            Permission.APPROVE_LOW_RISK,
            Permission.APPROVE_HIGH_RISK,
            Permission.APPROVE_CRITICAL,
        }
    ),
    Role.COMPLIANCE_OFFICER: frozenset(
        {
            Permission.ACCOUNT_READ,
            Permission.TRANSFER_READ,
            Permission.AUDIT_READ,
            Permission.REPORT_SUSPICIOUS,
            Permission.APPROVE_CRITICAL,
        }
    ),
    Role.ADMIN: frozenset(
        {
            Permission.ACCOUNT_READ,
            Permission.TRANSFER_READ,
            Permission.AUDIT_READ,
            Permission.USER_MANAGE,
        }
    ),
    Role.AUDITOR: frozenset({Permission.AUDIT_READ}),
    Role.SYSTEM: frozenset(set(Permission)),
}


def has_permission(roles: frozenset[Role], permission: Permission) -> bool:
    """Check if any of the given roles grant the specified permission."""
    for role in roles:
        perms = ROLE_PERMISSIONS.get(role, frozenset())
        if permission in perms:
            return True
    return False


# ── Maker-Checker ───────────────────────────────────────────────────


@dataclass(frozen=True)
class ApprovalRequirement:
    """Specification for who must approve an operation.

    Attributes:
        required_count: Number of distinct approvers required.
        distinct_from_requester: If True, the requester cannot approve.
        required_roles: Roles that can serve as approvers.
        require_different_roles: If True, approvers must have different roles.
        ttl_minutes: How long the approval window stays open.
    """

    required_count: int = 1
    distinct_from_requester: bool = True
    required_roles: frozenset[Role] = frozenset({Role.APPROVER, Role.BANKING_OFFICER})
    require_different_roles: bool = False
    ttl_minutes: int = 30


# ── Multi-tenant context ────────────────────────────────────────────


@dataclass(frozen=True)
class TenantConfig:
    """Per-tenant configuration for isolation and policy.

    Attributes:
        tenant_id: Unique tenant identifier.
        name: Human-readable tenant name.
        isolation_mode: "shared" or "dedicated" infrastructure.
        rate_limit_per_minute: Max requests per minute for this tenant.
        max_concurrent_sessions: Max concurrent agent sessions.
        allowed_currencies: Currencies this tenant can use.
        jurisdiction: Regulatory jurisdiction.
        data_residency: Geographic data storage requirement.
    """

    tenant_id: str
    name: str = ""
    isolation_mode: str = "shared"
    rate_limit_per_minute: int = 60
    max_concurrent_sessions: int = 10
    allowed_currencies: frozenset[str] = frozenset({"USD"})
    jurisdiction: str = ""
    data_residency: str = ""
