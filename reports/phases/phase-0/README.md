# Phase 0 — Project Contract and Reproducible Foundation

**Status:** COMPLETE
**Date:** 2026-06-21

## Exit Criteria Verification

| Criterion | Status | Detail |
|---|---|---|
| Pinned upstream verification passes | ✅ PASS | Upstream HEAD `5ebebbe827b455b3ed04fcb9294235c6ef4e5fd6` matches `UPSTREAM.lock` |
| Phase 0 tests pass | ✅ PASS | 38 passed, 0 failed |
| Ruff passes | ✅ PASS | `ruff check .` — All checks passed |
| Ruff format | ✅ PASS | `ruff format --check .` — 10 files already formatted |
| Mypy passes | ✅ PASS | `mypy src` — Success, no issues found in 4 source files |
| Evaluation-integrity boundaries documented | ✅ PASS | ADR 005 documents upstream read-only boundary |
| Evidence stored under reports/phases/phase-0/ | ✅ PASS | This report |

## Upstream Verification

```json
{
  "repository": "https://github.com/sierra-research/tau2-bench",
  "pinned_commit": "5ebebbe827b455b3ed04fcb9294235c6ef4e5fd6",
  "actual_commit": "5ebebbe827b455b3ed04fcb9294235c6ef4e5fd6",
  "branch": "main",
  "domain": "banking_knowledge",
  "match": true
}
```

## Commands Executed

| Command | Exit Code | Result |
|---|---|---|
| `uv run pytest tests/ -q` | 0 | 38 passed |
| `uv run ruff check .` | 0 | All checks passed |
| `uv run ruff format --check .` | 0 | 10 files already formatted |
| `uv run mypy src` | 0 | No issues found |
| `git diff --check` | 0 | No whitespace issues |

## Artifacts Created

- `src/fxfill_banking_agent/__init__.py` — Package metadata
- `src/fxfill_banking_agent/upstream.py` — UPSTREAM.lock parsing and commit verification
- `src/fxfill_banking_agent/config.py` — Typed configuration models (LLM, Database, MCP, Agent)
- `src/fxfill_banking_agent/evidence.py` — Evidence schemas for phase reporting
- `tests/unit/test_upstream.py` — 6 tests for upstream verification
- `tests/unit/test_config.py` — 16 tests for configuration validation
- `tests/unit/test_evidence.py` — 14 tests for evidence schemas
- `docs/adr/001-langgraph-agent-runtime.md` — ADR: LangGraph runtime
- `docs/adr/002-mcp-tool-boundaries.md` — ADR: MCP tool isolation
- `docs/adr/003-reasoning-validation-separation.md` — ADR: Reasoning–validation separation
- `docs/adr/004-authorization-before-side-effects.md` — ADR: Authorization gate
- `docs/adr/005-upstream-read-only.md` — ADR: Upstream read-only boundary
- `docs/development.md` — Local development guide

## Evaluation Integrity Boundaries

Benchmark integrity rules are documented in:
- `CLAUDE.md` — Benchmark Integrity section
- `docs/adr/005-upstream-read-only.md` — Concrete rules and consequences
- `.claude/rules/runtime.md` — Runtime module constraints
- `.claude/rules/testing.md` — Testing constraints

### Key boundaries

1. Never modify upstream tasks, policies, evaluators, or data.
2. Runtime code must never read evaluation criteria, reference actions, or expected outputs.
3. Never branch on benchmark task IDs.
4. Never hard-code benchmark answers.
5. Official evaluation must be run manually outside Claude Code.
6. Development tests use repository-owned fixtures under `evals/dev/`.
7. Treat the upstream repository as read-only.

## Unresolved Risks

- The `UPSTREAM.lock` `upstream_path` is relative (`../tau2-bench-upstream`) and must be present at development time.
- Mypy `strict = true` may require adjustments as the codebase grows.

## Deliberately Excluded (Future Phases)

- LangGraph runtime (Phase 1)
- Real LLM calls (Phase 2+)
- MCP servers (Phase 2+)
- PostgreSQL or Redis (Phase 3+)
- Human approval workflow (Phase 3)
- FastAPI or frontend (Phase 4+)
- Full benchmark execution (post-Phase 4)
