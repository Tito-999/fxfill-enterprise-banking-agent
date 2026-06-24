# BASELINE AUDIT — FxFill Enterprise Banking Agent

**Date:** 2026-06-24
**Branch:** main
**Commit:** 770eadf
**Auditor:** Claude Code (baseline audit per FxFill_Codex_P0_P3_Prompts.md Section 4)

## 1. Baseline Gate Results

| Gate | Result | Detail |
|---|---|---|
| pytest | ✅ 292 passed, 1 skipped | 20.73s |
| ruff check | ✅ All checks passed | — |
| ruff format | ✅ 88 files already formatted | — |
| mypy src | ✅ Success: no issues in 41 source files | — |

## 2. Twelve Risk Area Verification

### Risk 1: Provider sends tool schema to real model → ❌ GAP

**Severity: P0 BLOCKER**

- `LLMProvider` protocol (`llm.py:21`) only accepts `messages`, no `tools` parameter
- `DeepSeekProvider.invoke()` (`deepseek.py:47`) matches: no `tools` kwarg
- `_build_request_body()` (`deepseek.py:93-112`) builds body with `model`, `max_tokens`, `temperature`, `messages` — **no `tools` field**
- The model never receives tool definitions; Function Calling is impossible

**Evidence:** `src/fxfill_banking_agent/llm.py:21`, `src/fxfill_banking_agent/providers/deepseek.py:47,93-112`

### Risk 2: Provider request/response protocol consistency → ❌ GAP

**Severity: P0 BLOCKER**

- `_build_request_body()` (`deepseek.py:93-112`) uses Anthropic-compatible format (header `anthropic-version: 2023-06-01`)
- `_parse_response()` (`deepseek.py:146-198`) parses **OpenAI-compatible** format: `choices[0].message.tool_calls[].function.name/arguments`
- These are **incompatible protocols** — the request format doesn't match what the parser expects

**Evidence:** `src/fxfill_banking_agent/providers/deepseek.py:59-63,146-198`

### Risk 3: LangGraph compile binds checkpointer → ❌ GAP

**Severity: P0 BLOCKER**

- `graph.py:275`: `return builder.compile()` — **no checkpointer argument**
- `agent.py:55`: `SqliteCheckpointSaver` is created and stored in `self.checkpoint_saver`
- `agent.py:65`: `self._graph = build_agent_graph()` — checkpointer **never passed to graph**
- LangGraph cannot persist or restore state without a checkpointer bound at compile time

**Evidence:** `src/fxfill_banking_agent/graph.py:248-275`, `src/fxfill_banking_agent/agent.py:54-65`

### Risk 4: Same thread_id recovers history across requests/processes → ❌ GAP

**Severity: P0 BLOCKER**

- Consequence of Risk 3: without checkpointer bound to graph, LangGraph ignores `thread_id`
- `agent.py:119-131` passes `thread_id` in config but graph can't use it
- Multi-turn conversation requires checkpointer for state restoration

**Evidence:** `src/fxfill_banking_agent/agent.py:119-131`

### Risk 5: Bootstrap resources injected into AgentRuntime → ❌ PARTIAL

**Severity: P0**

- `bootstrap.py` creates: `hitl_store`, `grant_repo`, `idem_store`, `event_store`, `approval_executor`
- `api.py:126-131` creates `AgentRuntime(llm=llm, mcp_client=mcp_client, config=agent_cfg, auth_gateway=gateway)` — **missing**: `event_store`, `checkpoint_saver`, `idempotency_store`, `metrics_collector`
- `event_store` is given to `HITLApprovalExecutor` but NOT to `AgentRuntime`
- `checkpoint_saver` is **never explicitly created in bootstrap** (AgentRuntime creates its own internally)

**Evidence:** `src/fxfill_banking_agent/bootstrap.py:119-128`, `src/fxfill_banking_agent/api.py:126-131`

### Risk 6: HITL approval resumes the original graph → ❌ GAP

**Severity: P0 BLOCKER**

- `approval_executor.py:182`: `mcp_result = await self._mcp.call_tool(tool_call)` — **directly calls MCP**
- The tool result is returned to the API, NOT back into the LangGraph
- The model never sees the tool result, cannot generate a final answer, cannot continue reasoning
- No LangGraph `interrupt()` / `Command(resume=...)` pattern is used
- This is a **second execution path** that bypasses the graph entirely

**Evidence:** `src/fxfill_banking_agent/approval_executor.py:61-215`

### Risk 7: user_id/tenant_id/account ownership/approver identity from trusted context → ❌ GAP

**Severity: P0 BLOCKER**

- `api.py:178`: `user_id="default"` — **hardcoded string**
- `api.py:201`: `requesting_user_id="default"` — **hardcoded string**
- `api.py:53`: `approver: str = Field("human-operator")` — from **untrusted HTTP body**
- `actor_resolver.py:30-46`: `DevelopmentHeaderResolver` reads from HTTP header `X-Approver-Identity` — **spoofable**
- No `TrustedRequestContext` exists; no authentication middleware
- No tenant isolation whatsoever

**Evidence:** `src/fxfill_banking_agent/api.py:53,178,201`, `src/fxfill_banking_agent/actor_resolver.py:30-46`

### Risk 8: Tool risk classification uses name string matching → ❌ CONFIRMED

**Severity: P0**

- `graph.py:234-245`: `_classify_tool_kind()` uses `name.lower()` substring matching:
  - `"transfer"/"wire"/"send"/"pay"` → TRANSFER
  - `"delete"/"remove"/"purge"/"close"` → DELETE
  - `"update"/"modify"/"change"/"set"/"write"/"create"/"add"` → WRITE
  - else → READ
- No `ToolDefinition` model with explicit `side_effect`, `risk_level`, `permissions` fields
- Adding a tool named "get_transfer_status" would be incorrectly classified as TRANSFER

**Evidence:** `src/fxfill_banking_agent/graph.py:234-245`

### Risk 9: Per-step metrics are actually recorded → ❌ GAP

**Severity: P0**

- `metrics.py` defines `StepMetrics`, `RunMetrics`, `MetricsCollector` protocol, `InMemoryMetricsCollector`
- `agent.py:91`: `self.metrics_collector.start_run(run_id)` — called
- `agent.py:160`: `run_metrics = self.metrics_collector.finish_run()` — called
- But `record_step()` is **never called** — no per-step metrics are actually recorded
- Graph nodes don't have access to metrics collector to record per-step data

**Evidence:** `src/fxfill_banking_agent/agent.py:79-169`, `src/fxfill_banking_agent/graph.py:77-231`

### Risk 10: Benchmark runner is placeholder → ❌ CONFIRMED

**Severity: P1**

- `evaluation.py` defines data types (`EvalRunConfig`, `EvalRunResult`) and config profiles
- No actual benchmark runner implementation
- No integration with τ²-bench evaluation harness
- `EVAL_PROFILES` are configuration stubs, not executable evaluation

**Evidence:** `src/fxfill_banking_agent/evaluation.py:1-144`

### Risk 11: Tests use Fake Provider to fake key capabilities → ⚠️ CONFIRMED

**Severity: P0**

- `tests/fakes/llm.py` — `MockLLM` returns canned responses; never exercises real Function Calling
- `tests/fakes/mcp.py` — Stub MCP client
- `tests/fakes/transports.py` — Fake HTTP transports
- `tests/contract/test_live_provider.py` — likely skipped by default
- No E2E test exercises a real tool call through a real Provider

**Evidence:** `tests/fakes/`, `tests/contract/test_live_provider.py`, `src/fxfill_banking_agent/llm.py:33-91`

### Risk 12: README claims have test evidence → ❌ CONFIRMED

**Severity: P0**

- `README.md` is **0 bytes** (empty file)
- No capabilities are documented
- No test-to-claim mapping exists

**Evidence:** `README.md` (empty)

## 3. Additional Issues Found

### A. No ToolDefinition / ToolRegistry exists
The modification plan calls for `src/fxfill_banking_agent/tools/models.py`, `registry.py`, `validation.py`, `provider_adapters.py` — none exist. Tool definitions are scattered across MCP schemas and string matching.

### B. No structured AgentErrorCode
The plan calls for `AgentErrorCode(StrEnum)` — doesn't exist. Errors are ad-hoc `RuntimeError` and `HTTPException` with raw strings.

### C. No conversation_service.py or resume_service.py
Multi-turn session management and HITL resume logic are absent.

### D. No security/context.py, security/authentication.py, security/authorization.py
Trusted identity and authentication modules don't exist.

### E. No Prompt Registry, RAG, Memory, Intent Router, Planner/Executor/Verifier
All P1 capabilities are absent.

### F. No Dockerfile, compose.yaml, Kubernetes manifests, CI/CD
All P2 capabilities are absent.

### G. No OpenTelemetry integration
Observability beyond basic logging is absent.

## 4. Audit Conclusion

The codebase has 290+ well-structured tests and clean static analysis, but **all 12 critical risks are confirmed gaps**. The system has:

- A well-architected skeleton with proper separation of concerns
- Clean type annotations and test infrastructure
- But **the main execution chain is not wired**: Function Calling, checkpointer binding, HITL graph resume, trusted identity, and per-step metrics are all disconnected

**P0 gate: FAIL** — The main chain is not correctly wired. The system cannot perform real Function Calling, cannot persist/restore conversations, and the HITL workflow bypasses the agent graph.

## 5. Next Steps

Proceed to `docs/execution/P0_P3_EXECUTION_PLAN.md` for the detailed implementation plan addressing each gap.
