"""Audit and compliance (P2-05).

Append-only audit events with hash chaining for tamper evidence.
Every side-effecting operation produces an audit record with:
- Actor, tenant, session, thread
- Prompt/model/tool/knowledge versions
- Authorization decision and approval chain
- Execution result summary (redacted)
"""

from fxfill_banking_agent.audit.models import (
    AuditEvent,
    AuditEventKind,
    AuditIntegrityError,
    ComplianceEvidenceBundle,
    build_evidence_bundle,
)

__all__ = [
    "AuditEvent",
    "AuditEventKind",
    "AuditIntegrityError",
    "ComplianceEvidenceBundle",
    "build_evidence_bundle",
]
