"""Upstream lock parsing and commit verification.

Reads ``UPSTREAM.lock`` and verifies that the pinned upstream repository
checkout matches the expected commit.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class UpstreamLock:
    """Parsed contents of UPSTREAM.lock."""

    repository: str
    commit: str
    branch: str
    domain: str
    integration_mode: str
    upstream_path: str
    official_evaluation_mode: str
    python_requires: str

    @classmethod
    def from_lock_file(cls, path: Path | str = "UPSTREAM.lock") -> UpstreamLock:
        """Parse an UPSTREAM.lock file into an UpstreamLock instance.

        Args:
            path: Path to the lock file.

        Returns:
            A populated UpstreamLock.

        Raises:
            FileNotFoundError: If the lock file does not exist.
            ValueError: If a required key is missing.
        """
        lock_path = Path(path)
        if not lock_path.exists():
            raise FileNotFoundError(f"UPSTREAM.lock not found at {lock_path.resolve()}")

        raw: dict[str, str] = {}
        for line in lock_path.read_text().strip().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                raise ValueError(f"Invalid lock line (missing '='): {line!r}")
            key, _, value = line.partition("=")
            raw[key] = value

        required = (
            "repository",
            "commit",
            "branch",
            "domain",
            "integration_mode",
            "upstream_path",
            "official_evaluation_mode",
            "python_requires",
        )
        for field in required:
            if field not in raw:
                raise ValueError(f"Missing required key in UPSTREAM.lock: {field!r}")

        return cls(
            repository=raw["repository"],
            commit=raw["commit"],
            branch=raw["branch"],
            domain=raw["domain"],
            integration_mode=raw["integration_mode"],
            upstream_path=raw["upstream_path"],
            official_evaluation_mode=raw["official_evaluation_mode"],
            python_requires=raw["python_requires"],
        )


def verify_upstream_commit(lock: UpstreamLock) -> bool:
    """Verify the upstream repository HEAD matches the pinned commit.

    Args:
        lock: Parsed upstream lock.

    Returns:
        True if the upstream repo HEAD equals the pinned commit.

    Raises:
        FileNotFoundError: If the upstream path does not exist.
        subprocess.CalledProcessError: If git rev-parse fails.
    """
    upstream_dir = Path(lock.upstream_path).resolve()
    if not upstream_dir.is_dir():
        raise FileNotFoundError(f"Upstream directory not found: {upstream_dir}")

    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(upstream_dir),
        capture_output=True,
        text=True,
        check=True,
    )
    actual_commit = result.stdout.strip()
    return actual_commit == lock.commit
