#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path


PROJECT_ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR", Path.cwd())).resolve()

UPSTREAM_ROOT = Path("/mnt/f/projects/tau2-bench-upstream").resolve()
PRIVATE_EVAL_ROOT = Path("/mnt/f/projects/eval-results-private").resolve()

READ_DENY_ROOTS = (
    UPSTREAM_ROOT / "data",
    PRIVATE_EVAL_ROOT,
    PROJECT_ROOT / "evals" / "holdout",
    PROJECT_ROOT / "secrets",
)

WRITE_DENY_ROOTS = (
    UPSTREAM_ROOT,
    PRIVATE_EVAL_ROOT,
    PROJECT_ROOT / "evals" / "holdout",
    PROJECT_ROOT / "secrets",
)

DANGEROUS_PATTERNS = (
    r"\bgit\s+reset\s+--hard\b",
    r"\bgit\s+clean\s+-[A-Za-z]*f",
    r"\bgit\s+push\b[^\n]*--force\b",
    r"\bgit\s+push\s+-f\b",
    r"\brm\s+-rf\b",
    r"\bchmod\s+-R\s+777\b",
    r"\bmkfs(?:\.\w+)?\b",
    r"\bdd\s+if=",
)


def block(reason: str) -> None:
    print(reason, file=sys.stderr)
    raise SystemExit(2)


def resolve_path(raw_path: str, cwd: str) -> Path:
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = Path(cwd) / path
    return path.resolve(strict=False)


def is_under(path: Path, roots: tuple[Path, ...]) -> bool:
    for root in roots:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        block("Blocked: invalid hook input.")

    tool_name = str(payload.get("tool_name", ""))
    tool_input = payload.get("tool_input", {})
    cwd = str(payload.get("cwd") or PROJECT_ROOT)

    if tool_name in {"Read", "Edit", "Write"}:
        raw_path = tool_input.get("file_path")

        if raw_path:
            path = resolve_path(str(raw_path), cwd)

            if tool_name == "Read" and is_under(path, READ_DENY_ROOTS):
                block(f"Blocked read from protected path: {path}")

            if tool_name in {"Edit", "Write"} and is_under(path, WRITE_DENY_ROOTS):
                block(f"Blocked write to protected path: {path}")

    if tool_name == "Bash":
        command = str(tool_input.get("command", ""))
        normalized = command.replace("\\", "/")

        for pattern in DANGEROUS_PATTERNS:
            if re.search(pattern, command, flags=re.IGNORECASE):
                block(f"Blocked destructive command: {command}")

        if (
            "tau2-bench-upstream/data" in normalized
            or "/mnt/f/projects/eval-results-private" in normalized
        ):
            block(
                "Blocked shell access to benchmark data or private evaluation results."
            )

        if ".env" in normalized and ".env.example" not in normalized:
            block("Blocked shell access to environment-secret files.")

        if "tau2-bench-upstream" in normalized:
            upstream_write_pattern = (
                r"\b(?:rm|mv|touch|mkdir|rmdir|truncate|chmod|chown|tee)\b"
                r"|\bsed\s+-i\b"
                r"|\bgit\s+(?:checkout|switch|reset|clean|commit|merge|rebase|pull)\b"
            )

            if re.search(
                upstream_write_pattern,
                command,
                flags=re.IGNORECASE,
            ):
                block(
                    "Blocked command that may modify the read-only upstream repository."
                )


if __name__ == "__main__":
    main()
