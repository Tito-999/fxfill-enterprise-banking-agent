"""Trusted request context — the single source of identity for each request.

All identity fields (user_id, tenant_id, roles, account ownership) must
come from this context, which is populated by authentication middleware.

The model must never be able to override these fields through prompt
injection or tool argument manipulation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TrustedRequestContext:
    """Immutable identity context for a single request.

    Populated by authentication middleware before the agent graph runs.
    Injected into tool execution by the server — the model never sees
    or controls these values.

    Attributes:
        subject_id: Authenticated user/principal identifier.
        tenant_id: Tenant/organization identifier for multi-tenancy.
        roles: Set of role strings for RBAC.
        account_ids: Accounts this user is authorized to access.
        auth_session_id: Session identifier from the auth provider.
        request_id: Unique request identifier for tracing.
        correlation_id: Cross-service correlation identifier.
        source: How the identity was established (e.g. "oidc", "header", "test").
    """

    subject_id: str
    tenant_id: str = "default"
    roles: frozenset[str] = frozenset()
    account_ids: frozenset[str] = frozenset()
    auth_session_id: str = ""
    request_id: str = ""
    correlation_id: str = ""
    source: str = "unknown"

    def has_role(self, role: str) -> bool:
        """True if the subject has the given role."""
        return role in self.roles

    def can_access_account(self, account_id: str) -> bool:
        """True if the subject is authorized for this account."""
        if not self.account_ids:
            return True  # No account restriction
        return account_id in self.account_ids

    def is_same_tenant(self, other_tenant: str) -> bool:
        """True if the subject belongs to the given tenant."""
        return self.tenant_id == other_tenant

    def to_injection_dict(self) -> dict[str, Any]:
        """Return fields to inject into tool arguments at execution time."""
        return {
            "user_id": self.subject_id,
            "tenant_id": self.tenant_id,
        }


# Sentinel for unauthenticated requests
ANONYMOUS_CONTEXT = TrustedRequestContext(
    subject_id="anonymous",
    tenant_id="default",
    source="none",
)
