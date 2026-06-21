# AUDIT REPORT — Step 4 Final Operational Acceptance

**Date:** 2026-06-21
**Branch:** step4-finalization-codex-salvage
**Commit SHA:** 2484892
**Auditor:** Step 4 final operational acceptance gate

## 1. Defect Resolution Summary

| Defect | Title | Resolution | Tests |
|---|---|---|---|
| DEFECT 1 | Historical empty tool_call_id not behaviorally tested | 7 behavioral executor tests | `test_historical_reconciliation.py` |
| DEFECT 2 | Reconciliation not an explicit durable state | RECONCILIATION_REQUIRED across HITL/grant/events | v5 schema + executor + HTTP 409 |
| DEFECT 3 | Lifecycle doesn't prove provider/MCP cleanup | ApplicationResources class | `lifecycle.py` |
| DEFECT 4 | No real application lifecycle acceptance tests | 9 TestClient lifespan tests | `test_app_lifecycle.py` |
| DEFECT 5 | Bootstrap partial failure has no rollback | Validation-before-resources + try/except rollback | `test_bootstrap_rollback.py` |
| DEFECT 6 | Executor absence fails at request time, not construction | HITLConfigurationError at create_app | bootstrap + construction tests |

## 2. Production Code Paths Verified

### 2.1 RECONCILIATION_REQUIRED Gate
- **Code:** `approval_executor.py:88-110`
- **Behavior:** Empty `tool_call_id` → RECONCILIATION_REQUIRED before grant approval/idempotency reservation/MCP dispatch
- **Test:** `test_executor_empty_tool_call_id_requires_reconciliation`

### 2.2 Application Lifecycle
- **Code:** `api.py:132-143` — FastAPI lifespan with `ApplicationResources.close()`
- **Code:** `lifecycle.py` — Idempotent close, per-resource exception isolation
- **Test:** `test_app_lifespan_closes_all_owned_resources`

### 2.3 Bootstrap Rollback
- **Code:** `bootstrap.py:62-167` — Pure validation before resources, `try/except BaseException: await resources.close(); raise`
- **Test:** `test_bootstrap_rolls_back_after_mcp_connection`

### 2.4 Construction-Time HITL Guard
- **Code:** `api.py:101-112` — `HITLConfigurationError` when HITL deps present without executor
- **Code:** `api.py:241` — HTTP 501 defensive guard (unreachable in normal bootstrap)
- **Test:** `test_hitl_app_requires_executor_at_construction`

## 3. Test Coverage

| Category | Count | New in Step 4 Final |
|---|---|---|
| unit | 122 | +9 (bootstrap rollback) |
| contract | 32 | — |
| integration | 22 | — |
| security | 22 | — |
| recovery | 56 | +7 (historical reconciliation) |
| e2e | 36 | +9 (app lifecycle) |
| **Total** | **290** | **+25** |

## 4. Source-Level Scans (All Clean)

| Scan | Hits | Status |
|---|---|---|
| `tool_call_id.*fallback\|or.*tool_name` | 0 | ✅ |
| `request.approver.*authorize\|approving_actor_id=request` | 0 | ✅ |
| `RECONCILIATION_REQUIRED` | 11 across 6 files | ✅ |
| `status_code=501` | 1 defensive guard | ✅ |
| `ApplicationResources` + `lifespan` + `disconnect` | All present | ✅ |

## 5. Verification Commands

```
uv run pytest -q -ra            → 289 passed, 1 skipped, 290 collected
uv run ruff check .             → All checks passed
uv run ruff format --check .    → 88 files already formatted
uv run mypy src                 → Success: no issues in 41 source files
git diff --check                → Clean
```

## 6. Schema

- **Current version:** 5
- **v5 migration:** `_migrate_v5` adds `RECONCILIATION_REQUIRED` to `approved_operation_grants` CHECK constraint
- **v4 migration:** `_migrate_v4` adds `tool_call_id` column to `hitl_sessions`

## 7. Key Files Changed

| File | Change |
|---|---|
| `api.py` | +HITLConfigurationError, construction guard, lifespan, reconciliation 409 |
| `approval_executor.py` | Reconciliation gate, typed ApprovalResult |
| `bootstrap.py` | Validation-before-resources, ApplicationResources, rollback |
| `db.py` | v5 migration |
| `grant_repo.py` | `mark_reconciliation_required()` |
| `hitl_store.py` | `RECONCILIATION_REQUIRED` status |
| `persistence.py` | `EventKind.RECONCILIATION_REQUIRED` |
| `lifecycle.py` | **New** — ApplicationResources |
| `test_historical_reconciliation.py` | **New** — 7 behavioral tests |
| `test_app_lifecycle.py` | **New** — 9 lifecycle tests |
| `test_bootstrap_rollback.py` | **New** — 9 bootstrap tests |

## 8. Warnings

| Warning | Severity | Status |
|---|---|---|
| Starlette TestClient httpx deprecation | Low | External dependency (GAP-004) |
| LangGraph allowed_objects default | Low | External dependency (GAP-005) |

## 9. Conclusion

All six Step 4 operational defects are resolved with production code changes and
behavioral tests. The guard chain (RECONCILIATION_REQUIRED → HITLConfigurationError →
ApplicationResources close → bootstrap rollback) is complete and verified.

**STEP_4_READY_FOR_INDEPENDENT_REVIEW**
