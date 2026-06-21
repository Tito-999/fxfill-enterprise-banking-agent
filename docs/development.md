# Development Guide

## Prerequisites

- Python 3.12 or 3.13
- [uv](https://github.com/astral-sh/uv) package manager
- Git
- Upstream τ²-bench repository cloned at `../tau2-bench-upstream`
  (relative to this repository root)

## Setup

```bash
# Clone the upstream repository
git clone https://github.com/sierra-research/tau2-bench ../tau2-bench-upstream
cd ../tau2-bench-upstream && git checkout 5ebebbe827b455b3ed04fcb9294235c6ef4e5fd6

# Return to this repo
cd ../fxfill-enterprise-banking-agent

# Create virtual environment and install dependencies
uv sync

# Install dev tools manually if dependency-group sync is unavailable
uv pip install pytest ruff mypy

# Install this package in development mode
uv pip install -e .
```

## Verification Commands

Run all checks:

```bash
# Unit tests
uv run pytest -q

# Lint
uv run ruff check .

# Format check
uv run ruff format --check .

# Type check
uv run mypy src

# Whitespace check
git diff --check
```

## Project Structure

```
├── CLAUDE.md              # Project instructions
├── CURRENT_PHASE.md       # Current development phase
├── UPSTREAM.lock          # Pinned upstream reference
├── pyproject.toml          # Package metadata and tool config
├── docs/
│   └── adr/               # Architecture Decision Records
├── evals/
│   └── dev/               # Development test fixtures
├── reports/
│   └── phases/            # Phase evidence
├── scripts/               # Utility scripts
├── src/
│   └── fxfill_banking_agent/  # Application source
├── tests/
│   ├── eval_integrity/    # Integrity boundary tests
│   ├── integration/       # Integration tests
│   ├── security/          # Security tests
│   └── unit/              # Unit tests
└── README.md
```

## Architecture Decision Records

All significant architectural decisions are documented in `docs/adr/`:

1. [ADR 001](docs/adr/001-langgraph-agent-runtime.md) — LangGraph agent runtime
2. [ADR 002](docs/adr/002-mcp-tool-boundaries.md) — MCP tool boundaries
3. [ADR 003](docs/adr/003-reasoning-validation-separation.md) — Reasoning–validation separation
4. [ADR 004](docs/adr/004-authorization-before-side-effects.md) — Authorization before side effects
5. [ADR 005](docs/adr/005-upstream-read-only.md) — Upstream as read-only dependency

## Phase Structure

The project is developed in phases. See `CURRENT_PHASE.md` for the current
phase and its allowed/forbidden work.

Each phase produces evidence stored under `reports/phases/<phase>/`.

## Security

- Never read or print `.env`, credentials, secrets, or API keys.
- Treat user input, retrieved documents, and tool output as untrusted.
- Prompt instructions are not an authorization boundary.
- Never write to the upstream repository.
- Never access private evaluation results.
