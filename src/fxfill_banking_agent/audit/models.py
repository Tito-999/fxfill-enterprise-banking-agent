"""Audit models — append-only, hash-chained event records (P2-05)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class AuditEventKind(str, Enum):
    """Categories of auditable events."""

    AGENT_RUN_STARTED = "agent_run_started"
    LLM_CALL = "llm_call"
    TOOL_PROPOSED = "tool_proposed"
    AUTHORIZATION_DECISION = "authorization_decision"
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_GRANTED = "approval_granted"
    APPROVAL_REJECTED = "approval_rejected"
    TOOL_EXECUTED = "tool_executed"
    TOOL_FAILED = "tool_failed"
    FINAL_RESPONSE = "final_response"
    ERROR_OCCURRED = "error_occurred"
    CONFIG_CHANGED = "config_changed"


@dataclass(frozen=True)
class AuditEvent:
    """A single immutable audit record.

    Attributes:
        event_id: Unique event identifier.
        kind: Category of the event.
        actor_id: Who performed the action.
        tenant_id: Which tenant.
        session_id: Session identifier.
        thread_id: Conversation thread.
        timestamp: ISO-8601 UTC timestamp.
        details: Event-specific data (must be redacted before storage).
        previous_hash: SHA-256 of the previous event (for hash chaining).
        event_hash: SHA-256 of this event (computed at creation).
        prompt_version: Version of the prompt used (if applicable).
        model_version: Model identifier (if applicable).
        tool_version: Tool registry version (if applicable).
    """

    event_id: str
    kind: AuditEventKind
    actor_id: str = ""
    tenant_id: str = "default"
    session_id: str = ""
    thread_id: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    details: str = ""  # JSON-encoded, redacted
    previous_hash: str = ""
    event_hash: str = ""
    prompt_version: str = ""
    model_version: str = ""
    tool_version: str = ""

    @staticmethod
    def compute_hash(
        event_id: str,
        timestamp: str,
        kind: str,
        details: str,
        previous_hash: str,
    ) -> str:
        """Compute the SHA-256 hash of an event for the chain."""
        content = f"{event_id}|{timestamp}|{kind}|{details}|{previous_hash}"
        return hashlib.sha256(content.encode()).hexdigest()


class AuditIntegrityError(RuntimeError):
    """Raised when the audit hash chain is broken."""


@dataclass
class ComplianceEvidenceBundle:
    """A bundle of audit evidence for a compliance review.

    Attributes:
        bundle_id: Unique identifier.
        time_range_start: Start of the evidence window.
        time_range_end: End of the evidence window.
        event_count: Number of events in the bundle.
        hash_chain_verified: Whether the chain is intact.
        generated_at: When the bundle was created.
        controls_covered: List of compliance controls covered.
    """

    bundle_id: str
    time_range_start: str = ""
    time_range_end: str = ""
    event_count: int = 0
    hash_chain_verified: bool = False
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    controls_covered: list[str] = field(default_factory=list)


def build_evidence_bundle(
    bundle_id: str,
    events: list[AuditEvent],
    controls: list[str] | None = None,
) -> ComplianceEvidenceBundle:
    """Build a compliance evidence bundle from audit events.

    Verifies the hash chain integrity across all events.
    """
    chain_ok = True
    for i, event in enumerate(events):
        if i == 0:
            continue
        expected = AuditEvent.compute_hash(
            event.event_id,
            event.timestamp,
            event.kind.value,
            event.details,
            events[i - 1].event_hash,
        )
        if event.event_hash != expected:
            chain_ok = False
            break

    if events:
        start = events[0].timestamp
        end = events[-1].timestamp
    else:
        start = end = ""

    return ComplianceEvidenceBundle(
        bundle_id=bundle_id,
        time_range_start=start,
        time_range_end=end,
        event_count=len(events),
        hash_chain_verified=chain_ok,
        controls_covered=controls or [],
    )
