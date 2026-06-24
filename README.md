# FxFill Enterprise Banking Agent

Production-oriented banking knowledge and tool-use agent evaluated against
the public τ³-bench `banking_knowledge` environment.

**This is a portfolio reference implementation.** It does not process real
money, real customers, or real personal data.

## Verified Capabilities (P0 — 2026-06-24)

The following capabilities are backed by automated tests (292 tests pass):

| Capability | Evidence |
|---|---|
| Real Function Calling chain | LLM receives tool schemas via `ToolRegistry`; response tool calls parsed and validated |
| Durable LangGraph checkpointing | `SqliteCheckpointSaver` bound to graph; cross-request state recovery with `JsonPlusSerializer` |
| Multi-turn conversation persistence | Same `thread_id` recovers full message history via checkpointer |
| Typed tool metadata & validation | `ToolDefinition` with `side_effect`, `risk_level`, `permissions`; deterministic `validate_tool_call()` |
| HITL interrupt/resume | LangGraph `interrupt()` suspends before critical tools; `Command(resume=...)` resumes graph for model response |
| Authorization gateway | Three-phase: intent → deterministic authorization → execution; exact-match grant for approved operations |
| Durable idempotency | `IdempotencyStore` prevents duplicate side effects across restarts |
| Structured error codes | `AgentErrorCode` enum with safe, non-leaking client messages |
| Composition root | All resources (checkpointer, event store, idempotency, tool registry) wired through bootstrap |

## Known Limitations

- **Benchmark runner is a placeholder.** No official τ³-bench evaluation has been run.
- **Live Provider tests are opt-in.** Default test suite uses deterministic fake transports.
- **Identity context uses development defaults.** Production OIDC/JWT authentication is not yet implemented.
- **Approval executor still used for grant validation** alongside new graph resume path.

## Quick Start

```bash
# Install dependencies
uv sync --group dev

# Run tests
uv run pytest -q

# Quality gates
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

## Architecture

```
API (FastAPI) → AgentRuntime → LangGraph ReAct loop
                    ├── LLMProvider (DeepSeek, tools-enabled)
                    ├── MCPClient (banking tools)
                    ├── ToolRegistry (typed metadata)
                    ├── AuthorizationGateway
                    ├── CheckpointSaver (SQLite, durable)
                    ├── EventStore / MetricsCollector
                    └── HITL (graph interrupt/resume)
```

## Documentation

- `SPEC.md` — Project specification
- `ROADMAP.md` — Phase roadmap
- `AGENTS.md` — Engineering rules
- `docs/execution/STATUS.md` — Current execution status
- `docs/execution/DECISIONS.md` — Architecture decisions
- `docs/execution/BASELINE_AUDIT.md` — Baseline audit findings

## Benchmark Integrity

- Upstream τ³-bench is pinned in `UPSTREAM.lock` (commit `5ebebbe`)
- Official evaluation runs manually outside Claude Code
- No benchmark answers, evaluator internals, or gold states are accessed
- Development tests use repository-owned fixtures under `tests/`
