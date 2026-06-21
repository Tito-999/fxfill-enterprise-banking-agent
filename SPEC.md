# SPEC.md — fxfill-enterprise-banking-agent

**Version:** 0.1.0
**Status:** Draft (Phase 0)
**Date:** 2026-06-21

## 1. Problem

Evaluate a custom banking-knowledge agent against the public τ³-bench
`banking_knowledge` domain. The agent must retrieve and reason over
banking policy documents, execute domain tools through an isolated
MCP boundary, and respect deterministic authorization and security
rules — all without reading benchmark answers, rewards, or evaluation
internals.

This is a **portfolio reference implementation**. It does not process
real money, real customers, or real personal data.

## 2. Scope

### 2.1 In-Scope

| Area | Description |
|---|---|
| Agent runtime | LangGraph-based reasoning loop with explicit finite step limit |
| Tool boundary | MCP servers exposing banking-domain tools |
| Reasoning | LLM-driven intent selection, document retrieval, answer synthesis |
| Validation | Deterministic Python validators for tool arguments, auth, and business rules |
| Authorization | Explicit gate before every side-effecting operation; human-in-the-loop in later phases |
| Configuration | Typed, frozen dataclass models validated at construction |
| Persistence | Agent state checkpoints, conversation logs, audit trail (Phase 2+) |
| Evidence | Structured, machine-readable per-phase evidence under `reports/phases/` |
| Benchmark integration | External, pinned, read-only upstream; manual evaluation only |
| Observability | Structured logs, per-step traces, cost/latency metrics (Phase 2+) |

### 2.2 Out-of-Scope

| Area | Rationale |
|---|---|
| Real banking transactions | Reference implementation only |
| Real customer PII | Uses synthetic benchmark data |
| Production deployment | Portfolio project; no SLA |
| Regulatory compliance (SOX, PCI, GDPR) | Not a real financial system |
| Multi-tenancy | Single-agent evaluation |
| Custom LLM training or fine-tuning | Uses off-the-shelf models |
| Modification of benchmark tasks or evaluators | Benchmark-integrity rule |

## 3. Trust Boundaries

```
┌────────────────────────────────────────────────┐
│  Agent Runtime (this repository)               │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐ │
│  │ LLM      │  │ Deterministic  │  │ Auth Gate │ │
│  │ Reasoning│──│ Validators     │──│            │ │
│  └──────────┘  └──────────┘  └──────┬───────┘ │
│                                      │          │
└──────────────────────────────────────┼──────────┘
                                       │ MCP protocol
                              ┌────────▼──────────┐
                              │ MCP Tool Server    │
                              │ (separate process) │
                              └───────────────────┘
                                       │
                              ┌────────▼──────────┐
                              │ τ³-bench          │
                              │ (read-only, pinned)│
                              └───────────────────┘
```

- **LLM outputs** cross a trust boundary: every LLM-produced value
  reaching a side-effecting path must pass through a deterministic
  validator.
- **MCP protocol** is the only channel through which the agent
  invokes domain tools.
- **Upstream τ³-bench** is read-only; the agent runtime never imports
  evaluator internals, reference actions, expected outputs, or reward
  logic.
- **Prompt instructions are not an authorization boundary.**

## 4. Deterministic vs. Model-Driven Responsibilities

| Responsibility | Owner | Rationale |
|---|---|---|
| Tool selection | LLM | Requires NL reasoning about user intent |
| Tool argument construction | LLM | Extracts values from conversation + documents |
| Document retrieval query | LLM | Semantic search formulation |
| Answer synthesis | LLM | Natural-language response generation |
| Tool argument validation | Deterministic | Schema, types, ranges are machine-checkable |
| Authorization decision | Deterministic | Must be auditable and non-bypassable |
| Business rule enforcement | Deterministic | e.g., transfer limits, account ownership |
| Step limit enforcement | Deterministic | Hard loop bound, not prompt-based |
| Output sanitization | Deterministic | Strip PII, enforce format constraints |
| Evidence recording | Deterministic | Reproducible, not hallucinated |

## 5. Benchmark-Integrity Requirements

1. Never modify upstream tasks, policies, evaluators, or data.
2. Runtime code must never read evaluation criteria, reference actions,
   expected outputs, reward values, or gold database states.
3. Never branch on benchmark task IDs.
4. Never hard-code benchmark answers, expected tool calls, customer
   values, or reference trajectories.
5. Official benchmark and holdout evaluation run **manually outside
   Claude Code**.
6. Development tests use repository-owned fixtures under `evals/dev/`.
7. Treat the upstream repository as read-only.
8. Upstream commit is pinned in `UPSTREAM.lock` and verified at
   development and CI time.
9. Never access private evaluation results.

## 6. Authorization and Side-Effect Constraints

- Every side-effecting operation passes through a three-phase pipeline:
  1. **Intent** (LLM-produced)
  2. **Authorization gate** (deterministic)
  3. **Execution** (MCP server)
- In Phase 0–2, the authorization gate auto-approves in development.
- Phase 3 adds human-in-the-loop approval.
- Read operations may skip the authorization gate per policy.
- Authorization decisions are logged and auditable.

## 7. Configuration Requirements

- All configuration is typed, validated at construction, and frozen
  (`dataclass(frozen=True)`).
- Sensitive values (API keys, tokens, passwords) are read from the
  environment, never hard-coded or committed.
- Configuration covers: LLM provider/model, database URL, MCP server
  command, log level, environment, step limits, retry/timeout limits.
- See `src/fxfill_banking_agent/config.py` for the canonical schema.

## 8. Evidence and Reproducibility Requirements

- Every development phase produces structured evidence under
  `reports/phases/<phase>/`.
- Evidence includes: verification results, command records, artifact
  paths with hashes, timestamps, and phase status.
- Evidence must never contain secrets, tokens, benchmark answers, or
  private evaluation results.
- Evidence schema is defined in `src/fxfill_banking_agent/evidence.py`.
- Machine-readable evidence is stored as JSON alongside the human-readable
  summary.

## 9. Phase 0 Acceptance Criteria

| # | Criterion | Evidence |
|---|---|---|
| 1 | Upstream commit verified | `verify_upstream_commit()` passes |
| 2 | Package installs and imports | `import fxfill_banking_agent` succeeds |
| 3 | Configuration models validate and reject invalid input | 16 config tests pass |
| 4 | Evidence models support full workflow | 14 evidence tests pass |
| 5 | Upstream lock parsed correctly | 6 upstream tests pass |
| 6 | Ruff lint passes | `ruff check .` exits 0 |
| 7 | Ruff format passes | `ruff format --check .` exits 0 |
| 8 | Mypy strict passes | `mypy src` exits 0 |
| 9 | No LangGraph dependency installed | `grep -i langgraph pyproject.toml uv.lock` is empty |
| 10 | No MCP dependency installed | `grep -i mcp pyproject.toml uv.lock` is empty (except comments) |
| 11 | No real LLM calls | No `litellm`, `openai`, or `anthropic` SDK imports in our code |
| 12 | Benchmark answers not accessed | No imports from `tau2` evaluator or task internals |
| 13 | Upstream unchanged and clean | `git status` clean in upstream repo |
| 14 | ADRs cover all required subjects | 5 ADRs present |
| 15 | SPEC.md and ROADMAP.md present | This file and ROADMAP.md |
| 16 | Machine-readable evidence present | `reports/phases/phase-0/phase-0-evidence.json` |
