# AUDIT REPORT — Step 2: Acceptance and Hardening Gate

**Date:** 2026-06-21
**Commit:** d76dcbb (baseline) → hardening commit
**Auditor:** Automated acceptance gate

## 1. Production Execution Path Audit

### 1.1 FastAPI → AgentRuntime
**Finding:** ✅ VERIFIED
- `api.py:110-115` creates AgentRuntime with injected LLMProvider and MCPClient
- `api.py:144` calls `await runtime.run(request.message, run_id=request.session_id)`
- The real AgentRuntime executes, not a mock or stub

### 1.2 AgentRuntime → LangGraph
**Finding:** ✅ VERIFIED
- `agent.py:62` calls `build_agent_graph()`
- `agent.py:130` calls `self._graph.ainvoke(state, config=...)`
- The real compiled LangGraph graph executes

### 1.3 MockLLM/StubMCPClient in Production Path
**Finding:** ✅ NO — NOT USED IN DEFAULT PATH
- `api.py` and `agent.py` accept `LLMProvider` and `MCPClient` protocols only
- MockLLM, EchoLLM, StubMCPClient are concrete implementations in the same module
  but never imported by the production code path
- Marked with clear docstrings indicating test/demo use
- Protocol-based design allows test fakes to coexist in source (common Python pattern)

### 1.4 Authorization Before Side-Effecting Tool Calls
**Finding:** ✅ VERIFIED (FIXED IN HARDENING)
- `graph.py:135-152` — `_tool_node` now calls `auth_gateway.authorize(op)` before every tool call
- API layer: `api.py:126-141` authorizes top-level requests
- Graph layer: `graph.py:135-152` authorizes individual tool calls
- Both layers independently enforce authorization (defense in depth)

### 1.5 HITL Pause/Approval/Rejection/Resume
**Finding:** ⚠️ PARTIALLY IMPLEMENTED (FIXED IN HARDENING)
- PENDING decision model exists in `auth.py`
- `api.py:148-158` catches RuntimeError from tool_node (HITL pause) → returns 202
- `api.py:169-217` `/agent/approve` endpoint accepts approve/reject decisions
- In-memory session store for paused sessions
- Gap: No persistent session store (survives only within process lifetime)
- Gap: No notification mechanism (CLI prompt, webhook, etc.)

### 1.6 Persistence for Process Reconstruction
**Finding:** ⚠️ PARTIALLY IMPLEMENTED (FIXED IN HARDENING)
- `agent.py:64-75` now persists events through event_store
- SqliteEventStore supports querying events by run_id
- `agent.py:104-113` supports `resume_from_state` parameter
- Gap: MemorySaver checkpoint (in-memory only) — no SQLite checkpoint adapter wired
- Gap: Full reconstruction requires external coordination (state must be saved externally)

### 1.7 Side-Effect Idempotency
**Finding:** ✅ VERIFIED (FIXED IN HARDENING)
- `state.py:37` — `executed_tool_ids: set[str]` added to AgentState
- `graph.py:116-133` — tool_node skips already-executed tool calls
- `agent.py:110` — `resume_from_state` preserves executed tool IDs

### 1.8 Phase 5 Benchmark Execution
**Finding:** ❌ NOT VERIFIED — SCAFFOLD ONLY
- No official tau2-bench evaluation was executed
- `scripts/run_benchmark.py` contains a placeholder-result path
- Phase 5 reports have been corrected to reflect "evaluation harness implemented"

### 1.9 .env.example
**Finding:** ✅ VERIFIED
- `.claude/settings.json` denies Read of `.env` files
- Tracked credential scan matched only `.env.example`
- Security tests verify placeholder-only content

## 2. Production Code Fixes Applied

| Defect | Fix | File |
|---|---|---|
| Auth only at API layer, not in graph | Added auth check in `_tool_node` | `graph.py` |
| Event store never written during run() | Wire `_persist_event` in `run()` | `agent.py` |
| No HITL resume mechanism | Added `/agent/approve` endpoint | `api.py` |
| No idempotency for tool calls | Added `executed_tool_ids` tracking | `graph.py`, `state.py` |
| Phase 5 claims inaccurate | Corrected all reports | `reports/phases/phase-5/` |

## 3. Test Coverage

| Category | Tests | Files |
|---|---|---|
| Unit | 97 | 15 files in `tests/unit/` |
| Integration | 16 | 2 files in `tests/integration/` |
| Security | 17 | 1 file in `tests/security/` |
| Recovery | 6 | 1 file in `tests/recovery/` |
| End-to-end | 14 | 1 file in `tests/e2e/` |
| **Total** | **158** | **24 files** |

## 4. Warnings

| Warning | Severity | Status |
|---|---|---|
| Starlette TestClient httpx deprecation | Low | Recorded in known-gaps (external dep) |
| LangGraph allowed_objects default | Low | Recorded in known-gaps (external dep) |
