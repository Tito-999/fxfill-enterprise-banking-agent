# ROADMAP.md — fxfill-enterprise-banking-agent

**Version:** 0.1.0
**Date:** 2026-06-21

## Prohibited Scope Expansion

The following are **not** implemented in Phase 0:

- LangGraph runtime or dependency
- MCP server implementation or dependency
- Real LLM calls (no `litellm`, `openai`, or `anthropic` SDK usage)
- PostgreSQL, Redis, or any persistent database
- FastAPI, HTTP API, or web frontend
- Human approval workflow
- Official benchmark execution (manual only, outside Claude Code)

Any phase that introduces these capabilities must explicitly declare
them in its exit criteria and complete all prior phases first.

---

## Phase 0 — Project Contract and Reproducible Foundation

**Status:** Implemented

### Entry criteria
- Repository initialized
- Upstream τ³-bench cloned at pinned path
- Python ≥3.12, <3.14 available
- `uv` package manager installed

### Allowed work
- Project specification and roadmap
- Architecture Decision Records
- Upstream commit verification module
- Minimal Python package structure
- Typed configuration schemas
- Evidence schemas
- Phase 0 unit tests
- Local development documentation

### Forbidden work
- LangGraph runtime
- Real LLM calls
- MCP servers
- PostgreSQL or Redis
- Human approval workflow
- FastAPI or frontend
- Full benchmark execution
- Reading benchmark task answers or evaluation criteria
- Modifying the upstream repository

### Exit criteria
- [x] Pinned upstream verification passes
- [x] Phase 0 tests pass (38/38)
- [x] Ruff lint passes
- [x] Ruff format passes
- [x] Mypy strict passes
- [x] Evaluation-integrity boundaries documented
- [x] SPEC.md and ROADMAP.md present
- [x] Machine-readable evidence stored under `reports/phases/phase-0/`
- [x] ADRs cover project boundary, benchmark integrity, runtime framework,
      evaluation separation, tool boundaries, and authorization

### Dependencies
- Upstream τ²-bench repository at pinned commit

---

## Phase 1 — LangGraph Agent Scaffolding

**Status:** Planned (not started)

### Entry criteria
- All Phase 0 exit criteria met
- LangGraph and langchain-core added to project dependencies

### Allowed work
- LangGraph state graph definition
- LLM-backed agent node (mock or real LLM per environment)
- Tool-calling integration via MCP client
- Unit tests for graph structure, routing, and interrupts
- Checkpointing scaffold

### Forbidden work
- Production database integration
- Human approval workflow
- Official benchmark execution
- Multi-agent or complex routing

### Exit criteria
- Agent graph compiles and runs with mock LLM
- Tool calls route through MCP client stub
- Graph interrupts on checkpoint signal
- Tests pass, ruff, mypy clean

### Dependencies
- Phase 0
- LangGraph library

---

## Phase 2 — Durable Execution and Persistence

**Status:** Planned (not started)

### Entry criteria
- All Phase 1 exit criteria met
- SQLite (development) or PostgreSQL (optional) available

### Allowed work
- Conversation and event persistence
- Checkpoint storage and resume
- Structured logging
- Cost and latency metrics
- Integration tests with τ³-bench banking tools

### Forbidden work
- Human approval workflow
- Official benchmark execution
- Web frontend or public API

### Exit criteria
- Agent state survives restart
- Events are queryable
- Metrics are recorded per step
- Integration tests pass
- Ruff, mypy clean

### Dependencies
- Phase 1
- Database driver (sqlite/asyncpg)

---

## Phase 3 — Authorization and Human-in-the-Loop

**Status:** Planned (not started)

### Entry criteria
- All Phase 2 exit criteria met

### Allowed work
- Authorization gateway implementation
- Human approval UI or CLI prompt
- Approval audit trail
- Configurable approval policy (auto-approve, require-approval, deny)

### Forbidden work
- Official benchmark execution
- Modification of upstream evaluator

### Exit criteria
- Side-effecting operations require approval (when enabled)
- Approval decisions are logged
- Denied operations are blocked, not silently dropped
- Tests pass, ruff, mypy clean

### Dependencies
- Phase 2

---

## Phase 4 — API, Observability, and Full Integration

**Status:** Planned (not started)

### Entry criteria
- All Phase 3 exit criteria met

### Allowed work
- FastAPI service exposing agent as HTTP endpoint
- Request/response schemas
- OpenTelemetry integration
- Dashboard or health-check endpoint
- Security hardening (rate limiting, input sanitization)

### Forbidden work
- Official benchmark execution except per integrity rules

### Exit criteria
- Agent runs behind FastAPI
- Multiple concurrent requests handled correctly
- Telemetry exported
- Security review completed

### Dependencies
- Phase 3
- FastAPI, OpenTelemetry

---

## Phase 5 — Benchmark Evaluation and Tuning

**Status:** Planned (not started)

### Entry criteria
- All Phase 4 exit criteria met
- Human operator available for manual evaluation

### Allowed work
- Manual benchmark execution (outside Claude Code)
- Performance analysis against public metrics
- Agent configuration tuning
- Documentation of results

### Forbidden work
- Modifying benchmark tasks, evaluators, or gold data
- Automated evaluation loop against holdout set
- Reading private evaluation criteria

### Exit criteria
- At least one full benchmark run completed
- Results documented
- No benchmark-integrity violations

### Dependencies
- Phase 4

---

## Phase-to-Phase Dependency Graph

```
Phase 0 ──► Phase 1 ──► Phase 2 ──► Phase 3 ──► Phase 4 ──► Phase 5
  │           │           │           │           │           │
  └── specs   └── runtime  └── state   └── auth    └── serve   └── evaluate
```

No phase may begin before its dependencies are satisfied. No phase may
implement work listed as forbidden in earlier phases without updating
the earlier phase's exit criteria and re-verifying.
