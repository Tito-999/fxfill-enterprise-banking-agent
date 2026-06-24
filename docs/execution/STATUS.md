# Execution Status — FxFill Enterprise Banking Agent

**Last updated:** 2026-06-25  
**Branch:** `main`  
**Current maturity:** Enterprise-oriented reference implementation / production-like prototype  
**Production readiness:** Not approved for real customers, real funds, or sensitive banking data

## Executive Summary

FxFill now has a working, testable main path for synthetic banking queries and controlled tool use. The repository includes a FastAPI service, LangGraph runtime, DeepSeek provider integration, MCP-style banking tools, trusted identity propagation for the direct route, authorization checks, HITL scaffolding, durable SQLite state, Docker packaging, Kubernetes and CI assets, and a broad automated test suite.

The project is suitable as a portfolio-grade enterprise architecture reference implementation. It is **not yet a production banking system** because production authentication, distributed persistence, multi-instance consistency, complete HITL identity binding, operational observability, and external benchmark validation remain incomplete.

## Latest Verified Evidence

Local verification completed on 2026-06-25:

| Check | Result |
|---|---|
| Pytest | `384 passed, 1 skipped` |
| Line coverage | `68%` across `src/` |
| Ruff lint | Passed |
| Ruff format check | Passed |
| MyPy | Passed for the configured scope (`87` source files) |
| Docker image build | Passed |
| Docker Compose | `agent`, `postgres`, and `redis` reached `healthy` |
| API health check | `GET /health` returned `200` |
| Live provider smoke path | DeepSeek request returned `200` during manual smoke testing |
| Identity smoke test | `user-alice` could read `ACC-1001` |
| Cross-account isolation | `user-alice` was denied access to `ACC-2001` |
| Prompt identity spoofing | Prompt claiming to be `user-bob` did not bypass trusted identity |
| Missing identity | Account data was not returned |
| Secret hygiene | `.env` ignored; no tracked `.env`/`request.json`; common secret patterns not found in Git history scan |

Notes:

- The single skipped test is the opt-in live-provider test.
- Local verification does not replace GitHub Actions, release, security, or deployment validation.
- MyPy currently contains scoped `ignore_errors = true` overrides for several critical modules; therefore “MyPy passed” does not mean the whole security-critical codebase is strictly typed.

## Phase Status

| Phase | Status | Gate | Honest interpretation |
|---|---|---|---|
| Baseline audit | Complete | PASS | Major architectural gaps were documented and prioritized. |
| P0 — Main-chain correctness | Substantially complete | CONDITIONAL | Main query path, tool calling, checkpointing, authorization, identity injection, and local quality gates work; production auth, HITL identity binding, and some error/event wiring remain open. |
| P1 — Agent capabilities | Partial | NOT PASSED | Router, planner, verifier, memory, RAG, prompt registry, and model-routing modules exist, but several paths have limited coverage or incomplete production evidence. |
| P2 — Productionization | Scaffold / partial | NOT PASSED | Docker, Compose, Kubernetes, CI, security, IAM, audit, and reliability assets exist, but PostgreSQL/Redis are not yet the authoritative runtime stores and multi-instance correctness is unproven. |
| P3 — AgentOps | Scaffold | NOT PASSED | AgentOps, evaluation, observability, reliability, and governance modules exist but are not fully wired, tested, or operated. |

## P0 Detailed Status

| ID | Task | Status | Evidence | Remaining work |
|---|---|---|---|---|
| P0-01 | Real function-calling chain | Done for reference path | Provider accepts tools; tool calls are parsed; registry/validation code exists; contract and integration tests pass. | Expand adversarial schema validation and live-provider regression coverage. |
| P0-02 | Checkpointer and multi-turn sessions | Implemented | LangGraph checkpointer is bound; SQLite checkpoint and recovery tests pass. | Prove tenant-scoped thread isolation under distributed storage and multiple processes. |
| P0-03 | Composition root | Implemented | `bootstrap_app()` wires runtime dependencies and Docker startup succeeds. | Eliminate remaining “created but unused” production scaffolds. |
| P0-04 | Durable HITL interrupt/resume | Partial | Graph interrupt/resume path and recovery tests exist. | Remove parallel execution semantics, bind the real trusted subject/tenant to every HITL record, and close crash/unknown-outcome gaps. |
| P0-05 | Trusted identity | Partial | Direct-route `user_id` is injected from `TrustedRequestContext`; spoofing and cross-account tests pass. | Implement real OIDC/JWT validation; disable development identity headers in production; remove remaining hard-coded identity values. |
| P0-06 | Tool metadata and risk classification | Implemented | Typed tool metadata and deterministic authorization/validation modules exist. | Increase coverage of validation failure branches and obscure-name side effects. |
| P0-07 | Events, metrics, structured errors | Partial | Structured logging, metrics, error types, and correlation components exist. | Ensure every LLM/tool/auth/HITL lifecycle step reaches durable event storage; stop returning raw exception strings to clients. |
| P0-08 | Type checks, test credibility, documentation | Partial | 384 tests pass; Ruff and configured MyPy pass; README and status refreshed. | Remove critical-module MyPy ignores, raise meaningful coverage, and keep public claims aligned with evidence. |

## Important Architecture Reality

### Authoritative persistence

The current verified runtime still uses SQLite for checkpoints, HITL state, grants, idempotency, and events. PostgreSQL and Redis containers can start successfully, but they are not yet the authoritative storage and coordination layer for the main runtime path.

### Authentication

Development mode accepts identity headers. Production OIDC/JWT validation remains a scaffold and must not be treated as complete authentication.

### Multi-instance behavior

Kubernetes assets declare multiple replicas, but correctness is not yet demonstrated because some state and rate limiting remain local to a process or SQLite file. Horizontal scaling is therefore not production-safe yet.

### Benchmark status

The upstream `tau2-bench` repository is pinned read-only, but the official `banking_knowledge` benchmark has not been completed. The benchmark runner must be treated as a scaffold until official evaluation evidence is recorded.

## Current Blockers to Production-Like Readiness

1. Implement cryptographically verified OIDC/JWT authentication with issuer, audience, expiry, JWKS rotation, tenant, role, and scope validation.
2. Replace hard-coded/default identities in HITL and approval records with trusted subject and tenant values.
3. Unify graph resume and approval execution into one canonical side-effect path.
4. Make PostgreSQL the durable source of truth and Redis the distributed coordination/rate-limit/cache layer.
5. Add database migrations, connection pooling, transaction isolation, optimistic locking, and uniqueness constraints for idempotency.
6. Split liveness, readiness, and deep dependency health checks.
7. Restrict CORS and remove raw exception details from client responses.
8. Remove critical-module MyPy `ignore_errors` overrides.
9. Raise critical-path coverage to at least 90% and eliminate unexplained 0%-coverage production modules.
10. Make all GitHub Actions jobs green and enforce coverage/security/container gates.
11. Add concurrent duplicate-approval, crash-recovery, unknown-write-outcome, and multi-tenant isolation tests.
12. Run and record the official external benchmark and a live-provider regression suite.

## Coverage Priorities

Current total line coverage is 68%. The following categories require focused tests before any production-readiness claim:

- Authentication and IAM
- HITL approval and resume services
- PostgreSQL and distributed storage backends
- Tool schema validation and provider adapters
- Planner/executor/verifier failure paths
- Observability, redaction, reliability, and AgentOps
- Conversation lifecycle and tenant isolation
- Server startup/shutdown and dependency health behavior

Recommended targets:

- Overall line coverage: at least 85%
- Overall branch coverage: at least 75%
- Auth, authorization, HITL, idempotency, and tool validation: at least 90%
- No production-intended module should remain at 0% without an explicit `scaffold` label

## Next Execution Order

1. Close GitHub Actions failures and enforce a coverage threshold.
2. Complete production authentication and trusted HITL identity binding.
3. Unify side-effect execution and recovery semantics.
4. Wire PostgreSQL and Redis into the authoritative runtime path.
5. Add distributed concurrency, chaos, and recovery tests.
6. Remove strict-typing exemptions from critical modules.
7. Wire OpenTelemetry/metrics/audit exports and operational runbooks.
8. Complete external benchmark and live-provider regression evidence.
9. Cut a documented `v0.1.0` portfolio release.

## Definition of “Finished”

### Portfolio release

The project may be considered complete as a portfolio release when:

- all CI jobs are green;
- README and status claims match automated evidence;
- Docker quick start works from a clean clone;
- security and identity smoke tests are documented;
- known scaffolds are clearly labelled;
- a tagged release and short demonstration are published.

### Production-like prototype

Requires production authentication, authoritative PostgreSQL/Redis integration, multi-instance correctness, hardened API behavior, observability, recovery tests, and substantially higher critical-path coverage.

### Real banking production system

Cannot be established by this repository alone. It additionally requires organizational security, compliance, legal, risk, operations, data governance, certified integrations, penetration testing, disaster-recovery exercises, and controlled production deployment.
