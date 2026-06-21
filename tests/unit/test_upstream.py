"""Tests for upstream lock parsing and commit verification."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from fxfill_banking_agent.upstream import UpstreamLock, verify_upstream_commit

VALID_LOCK = """\
repository=https://github.com/sierra-research/tau2-bench
commit=abc123def456
branch=main
domain=banking_knowledge
integration_mode=external-pinned-upstream
upstream_path=../tau2-bench-upstream
official_evaluation_mode=manual-outside-claude-code
python_requires=>=3.12,<3.14
"""


class TestUpstreamLockParsing:
    """Tests for UpstreamLock.from_lock_file."""

    def test_parses_valid_lock(self, tmp_path: Path) -> None:
        lock_file = tmp_path / "UPSTREAM.lock"
        lock_file.write_text(VALID_LOCK)

        lock = UpstreamLock.from_lock_file(str(lock_file))

        assert lock.repository == "https://github.com/sierra-research/tau2-bench"
        assert lock.commit == "abc123def456"
        assert lock.branch == "main"
        assert lock.domain == "banking_knowledge"
        assert lock.integration_mode == "external-pinned-upstream"
        assert lock.upstream_path == "../tau2-bench-upstream"
        assert lock.official_evaluation_mode == "manual-outside-claude-code"
        assert lock.python_requires == ">=3.12,<3.14"

    def test_parses_real_lock_file(self) -> None:
        """The actual UPSTREAM.lock in the repo root must parse without error."""
        lock_path = Path(__file__).parent.parent.parent / "UPSTREAM.lock"
        lock = UpstreamLock.from_lock_file(str(lock_path))

        assert lock.repository.startswith("https://github.com/sierra-research/tau2-bench")
        assert len(lock.commit) == 40  # full SHA
        assert lock.domain == "banking_knowledge"

    def test_raises_on_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            UpstreamLock.from_lock_file(str(tmp_path / "nonexistent.lock"))

    def test_raises_on_missing_key(self, tmp_path: Path) -> None:
        lock_file = tmp_path / "UPSTREAM.lock"
        lock_file.write_text("repository=foo\ncommit=bar\n")  # missing fields

        with pytest.raises(ValueError, match="Missing required key"):
            UpstreamLock.from_lock_file(str(lock_file))

    def test_raises_on_invalid_line(self, tmp_path: Path) -> None:
        lock_file = tmp_path / "UPSTREAM.lock"
        lock_file.write_text("no_equals_sign\n")

        with pytest.raises(ValueError, match="missing '='"):
            UpstreamLock.from_lock_file(str(lock_file))

    def test_skips_blank_and_comment_lines(self, tmp_path: Path) -> None:
        lock_file = tmp_path / "UPSTREAM.lock"
        lock_file.write_text("# comment line\n\n" + VALID_LOCK)

        lock = UpstreamLock.from_lock_file(str(lock_file))
        assert lock.commit == "abc123def456"


class TestVerifyUpstreamCommit:
    """Tests for verify_upstream_commit."""

    def test_matching_commits(self, tmp_path: Path) -> None:
        upstream_dir = tmp_path / "upstream"
        upstream_dir.mkdir()

        lock = UpstreamLock(
            repository="https://github.com/sierra-research/tau2-bench",
            commit="abc123def456abc123def456abc123def456abc123de",
            branch="main",
            domain="banking_knowledge",
            integration_mode="external-pinned-upstream",
            upstream_path=str(upstream_dir),
            official_evaluation_mode="manual-outside-claude-code",
            python_requires=">=3.12,<3.14",
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="abc123def456abc123def456abc123def456abc123de\n",
                stderr="",
            )
            assert verify_upstream_commit(lock) is True

        mock_run.assert_called_once()

    def test_mismatched_commits(self, tmp_path: Path) -> None:
        upstream_dir = tmp_path / "upstream"
        upstream_dir.mkdir()

        lock = UpstreamLock(
            repository="https://github.com/sierra-research/tau2-bench",
            commit="abc123def456abc123def456abc123def456abc123de",
            branch="main",
            domain="banking_knowledge",
            integration_mode="external-pinned-upstream",
            upstream_path=str(upstream_dir),
            official_evaluation_mode="manual-outside-claude-code",
            python_requires=">=3.12,<3.14",
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="different_commit_hash\n", stderr=""
            )
            assert verify_upstream_commit(lock) is False

    def test_missing_upstream_dir(self, tmp_path: Path) -> None:
        lock = UpstreamLock(
            repository="https://github.com/sierra-research/tau2-bench",
            commit="abc123def456abc123def456abc123def456abc123de",
            branch="main",
            domain="banking_knowledge",
            integration_mode="external-pinned-upstream",
            upstream_path=str(tmp_path / "nonexistent"),
            official_evaluation_mode="manual-outside-claude-code",
            python_requires=">=3.12,<3.14",
        )

        with pytest.raises(FileNotFoundError):
            verify_upstream_commit(lock)

    def test_git_failure_raises(self, tmp_path: Path) -> None:
        upstream_dir = tmp_path / "upstream"
        upstream_dir.mkdir()

        lock = UpstreamLock(
            repository="https://github.com/sierra-research/tau2-bench",
            commit="abc123def456abc123def456abc123def456abc123de",
            branch="main",
            domain="banking_knowledge",
            integration_mode="external-pinned-upstream",
            upstream_path=str(upstream_dir),
            official_evaluation_mode="manual-outside-claude-code",
            python_requires=">=3.12,<3.14",
        )

        with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "git")):
            with pytest.raises(subprocess.CalledProcessError):
                verify_upstream_commit(lock)
