# P0–P3 Execution Plan — FxFill Enterprise Banking Agent

**Date:** 2026-06-24
**Based on:** BASELINE_AUDIT.md + FxFill_Enterprise_Agent_P0_P1_P2_Modification_Plan.md
**Status:** P0 ready for implementation

---

## Dependency DAG

```
P0-01 (Function Calling)
  └─► P0-02 (Checkpointer)
       └─► P0-03 (Composition Root)
            └─► P0-04 (HITL Resume)
                 ├─► P0-05 (Trusted Identity)
                 ├─► P0-06 (Tool Metadata)
                 └─► P0-07 (Events/Metrics/Errors)
                      └─► P0-08 (Type Check & Cleanup)

P0 gate PASS
  └─► P1-01 (Intent Router)
       ├─► P1-02 (Planner–Executor–Verifier)
       ├─► P1-03 (Memory)
       └─► P1-04 (RAG)
            └─► P1-05 (Prompt Registry)
                 └─► P1-06 (Model Routing/Cache)
                      └─► P1-07 (PostgreSQL/Redis)
                           └─► P1-08 (OTel/Evaluation)
                                └─► P1 gate PASS

P1 gate PASS
  └─► P2-01 (Containers/K8s) ─── parallel with ───┐
       P2-02 (IAM/Multi-tenant)                    │
       P2-03 (Banking Adapters)                    │
       P2-04 (Data Security)                       │
       P2-05 (Audit)                               │
       P2-06 (HA/DR/Chaos)                         │
       P2-07 (AI Security)                         │
       P2-08 (Governance)                          │
       P2-09 (CI/CD)                               │
            └─► All converge ─► P2 gate PASS        │
```

---

## P0: Main Chain Correctness

### P0-01: Real Function Calling Main Chain

**Current state:** absent — Provider has no `tools` parameter, request body doesn't include tools, protocol mismatch (Anthropic request / OpenAI response parsing)

**Target behavior:**
- `LLMProvider.invoke()` accepts `tools: list[ToolDefinition] | None`
- `DeepSeekProvider` converts ToolDefinitions to provider-native format and includes in request body
- Provider response parsing correctly extracts tool calls
- Tool call name validated against allowlist before execution
- Tool call args validated via JSON Schema / Pydantic before execution

**Files to modify:**
- `src/fxfill_banking_agent/llm.py` — Extend LLMProvider protocol with tools param
- `src/fxfill_banking_agent/providers/base.py` — Add ToolDefinition type
- `src/fxfill_banking_agent/providers/deepseek.py` — Add tools to request body, fix protocol mismatch
- `src/fxfill_banking_agent/graph.py` — Pass tools from registry to LLM invoke, add validation before execution
- `src/fxfill_banking_agent/agent.py` — Wire tool registry into config

**New files:**
- `src/fxfill_banking_agent/tools/__init__.py`
- `src/fxfill_banking_agent/tools/models.py` — ToolDefinition, ToolCallValidation
- `src/fxfill_banking_agent/tools/registry.py` — ToolRegistry
- `src/fxfill_banking_agent/tools/validation.py` — validate_tool_call()
- `src/fxfill_banking_agent/tools/provider_adapters.py` — convert tools to provider format

**New tests:**
- `tests/contract/test_provider_tools.py` — Provider request contains tools
- `tests/contract/test_tool_validation.py` — Validation rejects bad names/args
- `tests/e2e/test_live_tool_call.py` — Opt-in live smoke test

**Risks:** Protocol mismatch fix requires choosing one protocol (OpenAI-compatible recommended since parsing already uses it)
**Backward compatibility:** MockLLM/EchoLLM must accept new `tools` parameter
**Definition of Done:**
- [ ] Provider invoke accepts tools parameter
- [ ] Request body includes tools in correct protocol format
- [ ] Tool calls parsed from response
- [ ] Tool name allowlist validation active
- [ ] Tool arg schema validation active
- [ ] MockLLM and EchoLLM updated
- [ ] Opt-in live smoke test exists
- [ ] All existing tests still pass

---

### P0-02: LangGraph Checkpointer & Multi-turn Sessions

**Current state:** partial — SqliteCheckpointSaver exists, graph compiles without checkpointer

**Target behavior:**
- `build_agent_graph(checkpointer=...)` binds checkpointer at compile time
- Same `thread_id` recovers prior messages and state across requests
- New requests with existing thread_id submit only incremental HumanMessage
- Different users/tenants cannot read others' threads
- Conversation lifecycle: create, read, delete, archive

**Files to modify:**
- `src/fxfill_banking_agent/graph.py` — Accept and bind checkpointer parameter
- `src/fxfill_banking_agent/agent.py` — Pass checkpointer to graph, multi-turn message handling
- `src/fxfill_banking_agent/api.py` — Thread-aware API routes
- `src/fxfill_banking_agent/checkpoint_store.py` — Serializer hardening, schema version

**New files:**
- `src/fxfill_banking_agent/conversation_service.py` — Thread CRUD, lifecycle

**New tests:**
- `tests/e2e/test_multiturn_persistence.py` — Cross-request, cross-process recovery
- `tests/security/test_thread_isolation.py` — Cross-user/tenant rejection

**Risks:** Checkpoint serializer may fail on complex state objects (set[str], LangChain Messages)
**Backward compatibility:** API changes break existing clients that don't pass thread_id
**Definition of Done:**
- [ ] Graph compiled with checkpointer
- [ ] Same thread_id recovers prior conversation across processes
- [ ] Cross-user thread access returns 403/404
- [ ] Thread lifecycle API functional
- [ ] Checkpoint schema migration test passes

---

### P0-03: Composition Root & Dependency Injection

**Current state:** partial — Bootstrap creates resources but doesn't pass all to AgentRuntime

**Target behavior:**
- All bootstrap-created resources (checkpointer, event_store, idempotency_store, metrics_collector) injected into AgentRuntime
- Production mode fails fast on missing dependencies
- Application shutdown closes all resources
- Single source of truth for which resources exist

**Files to modify:**
- `src/fxfill_banking_agent/bootstrap.py` — Pass all resources through
- `src/fxfill_banking_agent/api.py` — Wire resources into AgentRuntime
- `src/fxfill_banking_agent/agent.py` — Accept all resources explicitly
- `src/fxfill_banking_agent/lifecycle.py` — Ensure all resources closeable

**New tests:**
- `tests/e2e/test_production_composition.py` — Verify all resources wired

**Risks:** Changing AgentRuntime constructor signature breaks tests
**Definition of Done:**
- [ ] All bootstrap resources reach AgentRuntime
- [ ] No "created but unused" resources
- [ ] Production mode rejects missing dependencies
- [ ] All resources close on shutdown

---

### P0-04: Durable HITL Interrupt/Resume

**Current state:** partial — HITL exists but bypasses graph

**Target behavior:**
- Graph interrupts before sensitive tool execution (LangGraph `interrupt()`)
- Approval API resumes graph with `Command(resume=...)`
- Tool executes within graph context; result reaches model
- Model generates final answer after seeing tool result
- Rejection appends error ToolMessage; model cannot retry same call
- Idempotency prevents double execution on duplicate approval

**Files to modify:**
- `src/fxfill_banking_agent/graph.py` — Add interrupt() before critical tool calls
- `src/fxfill_banking_agent/agent.py` — Support resume from interrupt
- `src/fxfill_banking_agent/approval_executor.py` — Replace direct-MCP with graph resume
- `src/fxfill_banking_agent/api.py` — Resume endpoint uses graph, not executor

**New files:**
- `src/fxfill_banking_agent/resume_service.py` — Resume orchestration

**New tests:**
- `tests/e2e/test_hitl_graph_resume.py` — Full interrupt→approve→resume→final_answer
- `tests/recovery/test_hitl_crash_recovery.py` — Restart after interrupt

**Risks:** LangGraph interrupt() API version compatibility; graph state serialization
**Definition of Done:**
- [ ] Graph interrupts before side-effecting tool
- [ ] Approval resumes graph (not bypass)
- [ ] Model sees tool result and generates answer
- [ ] Rejection blocks re-execution
- [ ] Duplicate approval safe
- [ ] Crash recovery works

---

### P0-05: Trusted Identity Context

**Current state:** absent — user_id hardcoded, approver from HTTP body

**Target behavior:**
- `TrustedRequestContext` created by authentication middleware
- Tool schemas exclude identity fields (server-injected)
- Account ownership checked before tool execution
- Cross-user and cross-tenant access blocked

**Files to modify:**
- `src/fxfill_banking_agent/api.py` — Auth middleware, context extraction
- `src/fxfill_banking_agent/actor_resolver.py` — Context-based resolution
- `src/fxfill_banking_agent/auth.py` — Identity-aware authorization
- `src/fxfill_banking_agent/banking/tools.py` — Server-injected identity
- `src/fxfill_banking_agent/graph.py` — Context injection before tool execution

**New files:**
- `src/fxfill_banking_agent/security/__init__.py`
- `src/fxfill_banking_agent/security/context.py` — TrustedRequestContext
- `src/fxfill_banking_agent/security/authentication.py` — Auth middleware
- `src/fxfill_banking_agent/security/authorization.py` — Identity-aware policy

**New tests:**
- `tests/security/test_trusted_context.py` — Identity injection, cross-account, cross-tenant

**Risks:** Breaking existing tests that don't provide auth context
**Definition of Done:**
- [ ] TrustedRequestContext defined and immutable
- [ ] Identity from auth middleware, not model
- [ ] Model-visible tool schemas exclude identity fields
- [ ] Cross-account access blocked
- [ ] Cross-tenant access blocked
- [ ] Approver identity not from HTTP body

---

### P0-06: Explicit Tool Metadata & Risk Classification

**Current state:** absent — uses substring matching on tool name

**Target behavior:**
- Every tool has ToolDefinition with explicit side_effect, risk_level, permissions, approval_policy
- ToolRegistry is single source of truth for authorization and provider schema
- Adding a non-obvious-name side-effecting tool still triggers approval
- `_classify_tool_kind()` replaced by metadata lookup

**Files to modify:**
- `src/fxfill_banking_agent/graph.py` — Replace _classify_tool_kind with registry lookup
- `src/fxfill_banking_agent/auth.py` — Use ToolDefinition metadata
- `src/fxfill_banking_agent/banking/tools.py` — Add metadata to all tools

**New files:** (created in P0-01)
- `src/fxfill_banking_agent/tools/models.py` — Extended ToolDefinition
- `src/fxfill_banking_agent/tools/registry.py` — ToolRegistry

**New tests:**
- `tests/unit/test_tool_metadata.py` — Classification correctness
- `tests/security/test_metadata_authorization.py` — Obscure-name tools

**Risks:** None (builds on P0-01 foundation)
**Definition of Done:**
- [ ] ToolDefinition includes side_effect, risk_level, permissions
- [ ] No substring-based risk classification in production path
- [ ] New critical tool with non-obvious name enters approval
- [ ] ToolRegistry is single source of truth

---

### P0-07: Events, Metrics, Structured Errors Wiring

**Current state:** partial — types exist, rarely called

**Target behavior:**
- Every step produces events: LLM request, tool call, auth decision, HITL pause/resume, final response
- Per-step metrics recorded (duration, tokens, tool count)
- API returns stable machine-readable error codes
- `correlation_id` traces through all events

**Files to modify:**
- `src/fxfill_banking_agent/graph.py` — Record events and metrics per step
- `src/fxfill_banking_agent/agent.py` — Metrics collector access in graph config
- `src/fxfill_banking_agent/metrics.py` — Structured recording
- `src/fxfill_banking_agent/providers/deepseek.py` — Token usage passthrough

**New files:**
- `src/fxfill_banking_agent/errors.py` — AgentErrorCode enum

**New tests:**
- `tests/unit/test_errors.py`
- `tests/integration/test_event_metrics_wiring.py`

**Risks:** None
**Definition of Done:**
- [ ] per-step events in event store
- [ ] per-step metrics recorded
- [ ] Structured error codes on API responses
- [ ] correlation_id in all events

---

### P0-08: Type Check & Test Credibility Cleanup

**Current state:** mypy passes but code has gaps

**Target behavior:**
- No `ignore_errors = true` on critical modules (Provider, MCP, Auth, HITL)
- README documents only test-verified capabilities
- Benchmark placeholder explicitly marked
- Fake tests and real tests clearly separated

**Files to modify:**
- `pyproject.toml` — Review mypy overrides
- `README.md` — Write from test evidence
- `ROADMAP.md` — Update for P0 completion

**New tests:**
- Verify no test uses impossible real-provider responses while claiming E2E

**Risks:** None
**Definition of Done:**
- [ ] Critical path modules pass strict mypy
- [ ] README claims backed by test evidence
- [ ] Benchmark placeholder marked
- [ ] Test layers clearly documented

---

## P1: Enterprise Agent Capabilities

*(Detailed plan to be refined after P0 gate passes. Summary below.)*

### P1-01: Intent Router
- New: `src/fxfill_banking_agent/routing/` (intent.py, classifier.py, policies.py, router.py)
- Simple reads → direct tool workflow; knowledge → RAG; complex → Planner
- Tests: confusion matrix, simple-task-bypasses-planner

### P1-02: Planner–Executor–Verifier
- New: `src/fxfill_banking_agent/orchestration/` (planner.py, executor.py, verifier.py)
- Structured plans, plan validation, step execution, result verification
- Tests: 30+ multi-step regression tasks

### P1-03: Memory
- New: `src/fxfill_banking_agent/memory/` (models.py, working.py, summary.py, semantic.py, retention.py, redaction.py)
- Working/Summary/Semantic/Episodic layers
- Tests: 50+ round context maintenance, deletion verification

### P1-04: RAG
- New: `src/fxfill_banking_agent/rag/` (ingestion/, retrieval/, generation/, evaluation/)
- Versioned documents, hybrid retrieval, citations, anti-injection
- Tests: recall, groundedness, citation correctness, stale-policy

### P1-05: Prompt Registry
- New: `prompts/` directory with YAML templates
- Versioned, hashed, traceable prompts
- Tests: snapshot/contract tests

### P1-06: Model Routing & Cache
- Intent/risk/complexity-based routing
- Semantic cache with safety boundaries
- Tests: latency, cost, cache-hit metrics

### P1-07: PostgreSQL/Redis
- Alembic migrations, outbox pattern, concurrent control
- Tests: dual-instance idempotency

### P1-08: Observability & Evaluation
- OpenTelemetry traces, eval datasets, CI quality gates
- Tests: metric regression thresholds

---

## P2: Financial Productionization

*(High-level summary — detailed plan to be refined after P1 gate passes.)*

### P2-01: Containers & Kubernetes
- Dockerfile, compose.yaml, Helm charts, K8s manifests

### P2-02: IAM & Multi-tenancy
- OIDC/JWT, RBAC/ABAC, Maker-Checker, tenant isolation

### P2-03: Real Banking Adapters
- CoreBankingPort, PaymentsPort, AMLPort with sandbox adapters

### P2-04: Data Security
- Classification, encryption, redaction, retention

### P2-05: Audit & Compliance
- Append-only audit, hash chaining, evidence bundles

### P2-06: HA/DR/Chaos
- SLOs, circuit breakers, reconciliation, chaos tests

### P2-07: AI Security
- Red-team harness, injection defense, regression corpus

### P2-08: Governance
- Model/Prompt/Tool/Knowledge registries, release manifests

### P2-09: CI/CD & Supply Chain
- GitHub Actions, SBOM, secret scanning, provenance

---

## P3: AgentOps & Continuous Operations

*(See docs/ENTERPRISE_AGENT_P3_PLAN.md — to be created after P2)*

---
