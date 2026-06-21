"""Evidence schemas for structured phase reports and evaluation artifacts.

All evidence is stored under ``reports/phases/<phase>/``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional


class EvidenceStatus(str, Enum):
    """Status of an evidence artifact."""

    PASS = "pass"
    FAIL = "fail"
    SKIPPED = "skipped"
    ERROR = "error"


class PhaseStatus(str, Enum):
    """Phase completion status."""

    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class VerificationResult:
    """A single verification check result.

    Attributes:
        name: Human-readable check name.
        status: Outcome of the check.
        detail: Optional detail message.
        duration_ms: Wall-clock duration in milliseconds.
    """

    name: str
    status: EvidenceStatus
    detail: Optional[str] = None
    duration_ms: float = 0.0


@dataclass
class PhaseEvidence:
    """Aggregated evidence for a development phase.

    Attributes:
        phase: Phase identifier (e.g. "phase-0").
        status: Phase completion status.
        verifications: List of verification results.
        commands: Shell commands executed with their outputs.
        artifacts: Paths to evidence artifacts.
        started_at: ISO-8601 start timestamp.
        completed_at: ISO-8601 completion timestamp.
    """

    phase: str
    status: PhaseStatus = PhaseStatus.IN_PROGRESS
    verifications: list[VerificationResult] = field(default_factory=list)
    commands: list[CommandRecord] = field(default_factory=list)
    artifacts: list[Path] = field(default_factory=list)
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None

    def add_verification(self, result: VerificationResult) -> None:
        """Append a verification result."""
        self.verifications.append(result)

    def add_command(self, record: CommandRecord) -> None:
        """Append a command execution record."""
        self.commands.append(record)

    def add_artifact(self, path: Path) -> None:
        """Register an evidence artifact path."""
        self.artifacts.append(path)

    def mark_complete(self) -> None:
        """Mark the phase as complete with a timestamp."""
        self.status = PhaseStatus.COMPLETE
        self.completed_at = datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class CommandRecord:
    """Record of an executed verification command.

    Attributes:
        command: The exact command string that was executed.
        exit_code: Process exit code.
        stdout: Captured standard output.
        stderr: Captured standard error.
        duration_ms: Wall-clock duration in milliseconds.
    """

    command: str
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    duration_ms: float = 0.0


def evidence_dir(phase: str) -> Path:
    """Return the evidence directory for a phase.

    Args:
        phase: Phase identifier (e.g. "phase-0").

    Returns:
        Resolved path under ``reports/phases/<phase>/``.
    """
    return Path("reports/phases").resolve() / phase
