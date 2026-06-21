# Phase 4 — API, Observability, and Full Integration

**Status:** COMPLETE — Finalized with Step 4 operational acceptance (2026-06-21)
**Final commit:** 2484892

## Exit Criteria

| Criterion | Status | Detail |
|---|---|---|
| FastAPI service | ✅ PASS | `/health`, `/agent`, `/agent/approve` endpoints |
| Request/response schemas | ✅ PASS | Pydantic models with validation |
| Health-check endpoint | ✅ PASS | Returns version and status |
| Authorization in API | ✅ PASS | Auth gateway checks each request |
| Durable HITL persistence | ✅ PASS | SqliteHITLStore + GrantRepository + SqliteIdempotencyStore |
| Durable execution events | ✅ PASS | SqliteEventStore with full event lifecycle |
| Approval executor | ✅ PASS | HITLApprovalExecutor as sole production approval path |
| RECONCILIATION_REQUIRED state | ✅ PASS | Explicit domain outcome for historical records |
| Application lifecycle | ✅ PASS | ApplicationResources with idempotent close |
| Bootstrap rollback | ✅ PASS | Pure validation before resources; rollback on failure |
| Construction-time HITL guard | ✅ PASS | HITLConfigurationError at create_app / bootstrap |
| v5 schema migration | ✅ PASS | RECONCILIATION_REQUIRED in grant CHECK constraint |
| Tests pass | ✅ PASS | 290 collected, 289 passed, 1 skipped |
| Ruff passes | ✅ PASS | All checks passed |
| Ruff format passes | ✅ PASS | 88 files formatted |
| Mypy strict | ✅ PASS | No issues in 41 source files |

## Test Counts by Category

| Category | Tests |
|---|---|
| unit | 122 |
| contract | 32 |
| integration | 22 |
| security | 22 |
| recovery | 56 |
| e2e | 36 |
| **Total** | **290** (289 passed, 1 skipped) |

## New Files in Step 4 Finalization

| File | Purpose |
|---|---|
| `src/fxfill_banking_agent/lifecycle.py` | ApplicationResources lifecycle owner |
| `tests/recovery/test_historical_reconciliation.py` | 7 behavioral tests for empty tool_call_id → RECONCILIATION_REQUIRED |
| `tests/e2e/test_app_lifecycle.py` | 9 lifecycle acceptance tests (close, idempotent, failure isolation) |
| `tests/unit/test_bootstrap_rollback.py` | 9 bootstrap rollback tests |

## Dependencies

- `fastapi>=0.138.0`
- `uvicorn>=0.49.0`
- `aiosqlite>=0.22.0`
