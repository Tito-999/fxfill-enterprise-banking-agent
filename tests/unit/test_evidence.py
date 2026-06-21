"""Tests for evidence schemas."""

from __future__ import annotations

from pathlib import Path

from fxfill_banking_agent.evidence import (
    CommandRecord,
    EvidenceStatus,
    PhaseEvidence,
    PhaseStatus,
    VerificationResult,
    evidence_dir,
)


class TestVerificationResult:
    def test_creation(self) -> None:
        vr = VerificationResult(
            name="upstream-verified",
            status=EvidenceStatus.PASS,
            detail="Commit matches",
            duration_ms=12.5,
        )
        assert vr.name == "upstream-verified"
        assert vr.status == EvidenceStatus.PASS
        assert vr.detail == "Commit matches"
        assert vr.duration_ms == 12.5

    def test_default_detail(self) -> None:
        vr = VerificationResult(name="check", status=EvidenceStatus.SKIPPED)
        assert vr.detail is None
        assert vr.duration_ms == 0.0


class TestCommandRecord:
    def test_creation(self) -> None:
        cr = CommandRecord(
            command="uv run pytest -q",
            exit_code=0,
            stdout="5 passed",
            stderr="",
            duration_ms=1500.0,
        )
        assert cr.command == "uv run pytest -q"
        assert cr.exit_code == 0
        assert cr.stdout == "5 passed"
        assert cr.stderr == ""
        assert cr.duration_ms == 1500.0

    def test_failed_command(self) -> None:
        cr = CommandRecord(
            command="uv run pytest -q",
            exit_code=1,
            stdout="",
            stderr="1 failed",
            duration_ms=500.0,
        )
        assert cr.exit_code == 1
        assert cr.stderr == "1 failed"


class TestPhaseEvidence:
    def test_initial_state(self) -> None:
        pe = PhaseEvidence(phase="phase-0")
        assert pe.phase == "phase-0"
        assert pe.status == PhaseStatus.IN_PROGRESS
        assert pe.verifications == []
        assert pe.commands == []
        assert pe.artifacts == []
        assert pe.started_at is not None
        assert pe.completed_at is None

    def test_add_verification(self) -> None:
        pe = PhaseEvidence(phase="phase-0")
        pe.add_verification(VerificationResult(name="test", status=EvidenceStatus.PASS))
        assert len(pe.verifications) == 1
        assert pe.verifications[0].name == "test"

    def test_add_command(self) -> None:
        pe = PhaseEvidence(phase="phase-0")
        pe.add_command(CommandRecord(command="echo hi", exit_code=0))
        assert len(pe.commands) == 1

    def test_add_artifact(self) -> None:
        pe = PhaseEvidence(phase="phase-0")
        pe.add_artifact(Path("reports/phases/phase-0/summary.md"))
        assert len(pe.artifacts) == 1

    def test_mark_complete(self) -> None:
        pe = PhaseEvidence(phase="phase-0")
        pe.mark_complete()
        assert pe.status == PhaseStatus.COMPLETE
        assert pe.completed_at is not None

    def test_aggregated_workflow(self) -> None:
        """Simulate a real evidence collection workflow."""
        pe = PhaseEvidence(phase="phase-0")

        pe.add_verification(
            VerificationResult(
                name="upstream-commit",
                status=EvidenceStatus.PASS,
                detail="5ebebbe matches",
                duration_ms=8.0,
            )
        )
        pe.add_verification(
            VerificationResult(
                name="pytest",
                status=EvidenceStatus.PASS,
                detail="all tests pass",
                duration_ms=1200.0,
            )
        )
        pe.add_command(
            CommandRecord(
                command="uv run pytest -q",
                exit_code=0,
                stdout="5 passed",
                duration_ms=1200.0,
            )
        )
        pe.mark_complete()

        assert len(pe.verifications) == 2
        assert len(pe.commands) == 1
        assert pe.status == PhaseStatus.COMPLETE
        assert pe.completed_at is not None


class TestEvidenceDir:
    def test_returns_correct_path(self) -> None:
        path = evidence_dir("phase-0")
        assert path.name == "phase-0"
        assert "reports" in str(path)
        assert "phases" in str(path)

    def test_different_phases(self) -> None:
        p0 = evidence_dir("phase-0")
        p1 = evidence_dir("phase-1")
        assert p0.name == "phase-0"
        assert p1.name == "phase-1"
        assert p0 != p1
