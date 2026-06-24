"""Unit tests for audit models and hash chain integrity."""

from __future__ import annotations

from fxfill_banking_agent.audit.models import (
    AuditEvent,
    AuditEventKind,
    build_evidence_bundle,
)


class TestAuditEvent:
    def test_event_creation(self) -> None:
        event = AuditEvent(
            event_id="evt-1",
            kind=AuditEventKind.AGENT_RUN_STARTED,
            actor_id="user-alice",
            tenant_id="t1",
        )
        assert event.kind == AuditEventKind.AGENT_RUN_STARTED
        assert event.actor_id == "user-alice"
        assert event.tenant_id == "t1"

    def test_compute_hash_deterministic(self) -> None:
        h1 = AuditEvent.compute_hash("evt-1", "2024-01-01", "agent_run_started", "{}", "")
        h2 = AuditEvent.compute_hash("evt-1", "2024-01-01", "agent_run_started", "{}", "")
        assert h1 == h2  # Deterministic

    def test_compute_hash_different_input(self) -> None:
        h1 = AuditEvent.compute_hash("evt-1", "2024-01-01", "agent_run_started", "{}", "")
        h2 = AuditEvent.compute_hash("evt-2", "2024-01-01", "agent_run_started", "{}", "")
        assert h1 != h2  # Different event_id → different hash


class TestHashChain:
    def test_chain_integrity(self) -> None:
        e1 = AuditEvent(
            event_id="evt-1",
            kind=AuditEventKind.AGENT_RUN_STARTED,
            timestamp="2024-01-01T00:00:00+00:00",
            details="{}",
            event_hash=AuditEvent.compute_hash(
                "evt-1", "2024-01-01T00:00:00+00:00", "agent_run_started", "{}", ""
            ),
        )
        e2 = AuditEvent(
            event_id="evt-2",
            kind=AuditEventKind.TOOL_EXECUTED,
            timestamp="2024-01-01T00:00:01+00:00",
            details='{"tool":"get_balance"}',
            previous_hash=e1.event_hash,
            event_hash=AuditEvent.compute_hash(
                "evt-2",
                "2024-01-01T00:00:01+00:00",
                "tool_executed",
                '{"tool":"get_balance"}',
                e1.event_hash,
            ),
        )
        assert e2.previous_hash == e1.event_hash


class TestEvidenceBundle:
    def test_empty_bundle(self) -> None:
        bundle = build_evidence_bundle("bundle-1", [])
        assert bundle.event_count == 0
        assert bundle.hash_chain_verified

    def test_valid_chain(self) -> None:
        e1 = AuditEvent(
            event_id="e1",
            kind=AuditEventKind.AGENT_RUN_STARTED,
            timestamp="2024-01-01T00:00:00+00:00",
            details="{}",
            event_hash=AuditEvent.compute_hash(
                "e1", "2024-01-01T00:00:00+00:00", "agent_run_started", "{}", ""
            ),
        )
        e2 = AuditEvent(
            event_id="e2",
            kind=AuditEventKind.TOOL_EXECUTED,
            timestamp="2024-01-01T00:00:01+00:00",
            details="{}",
            previous_hash=e1.event_hash,
            event_hash=AuditEvent.compute_hash(
                "e2", "2024-01-01T00:00:01+00:00", "tool_executed", "{}", e1.event_hash
            ),
        )
        bundle = build_evidence_bundle("b1", [e1, e2], ["control-1"])
        assert bundle.hash_chain_verified
        assert bundle.event_count == 2
        assert "control-1" in bundle.controls_covered

    def test_broken_chain_detected(self) -> None:
        e1 = AuditEvent(
            event_id="e1",
            kind=AuditEventKind.AGENT_RUN_STARTED,
            timestamp="2024-01-01T00:00:00+00:00",
            details="{}",
            event_hash="hash1",
        )
        e2 = AuditEvent(
            event_id="e2",
            kind=AuditEventKind.TOOL_EXECUTED,
            timestamp="2024-01-01T00:00:01+00:00",
            details="{}",
            previous_hash="wrong_hash",  # Mismatch
            event_hash="hash2",
        )
        bundle = build_evidence_bundle("b1", [e1, e2])
        assert not bundle.hash_chain_verified
