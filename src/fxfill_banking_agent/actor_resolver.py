"""Trusted approval actor resolution.

Production identity comes from authenticated request context.
Development mode uses a configured header; fails closed when missing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class TrustedActor:
    actor_id: str
    source: str  # "header", "token", "development"


class ApprovalActorResolver(Protocol):
    """Resolves the trusted identity of the approving actor.

    Never trusts the client-controlled request body approver field.
    """

    def resolve(self, context: dict | None) -> TrustedActor | None:
        """Return the trusted actor or None if identity is missing."""
        ...


class DevelopmentHeaderResolver:
    """Development resolver that reads from a configured HTTP header.

    Production must replace this with an authenticated context resolver.
    """

    def __init__(self, header_name: str = "X-Approver-Identity") -> None:
        self._header = header_name.lower()

    def resolve(self, context: dict | None) -> TrustedActor | None:
        if context is None:
            return None
        headers = context.get("headers", {})
        identity = headers.get(self._header, "")
        if not identity:
            return None
        return TrustedActor(actor_id=identity, source="header")


class FixedActorResolver:
    """Deterministic resolver for testing."""

    def __init__(self, actor_id: str = "test-operator") -> None:
        self._actor_id = actor_id

    def resolve(self, context: dict | None) -> TrustedActor | None:
        return TrustedActor(actor_id=self._actor_id, source="test")
