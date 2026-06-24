# Test Evidence — FxFill Enterprise Banking Agent

**Started:** 2026-06-24

## Baseline (2026-06-24, commit 770eadf)

```
uv run pytest -q -ra → 292 passed, 1 skipped in 20.73s
uv run ruff check . → All checks passed!
uv run ruff format --check . → 88 files already formatted
uv run mypy src → Success: no issues found in 41 source files
```

## P0-01: Real Function Calling (Pending)

No evidence yet. Tests to be added:
- Contract test: Provider request body contains tools field
- Contract test: Tool schema format matches provider protocol
- Contract test: Response parsing extracts tool calls correctly
- E2E test: Real model tool call smoke test (opt-in, skipped by default)

## P0-02: Checkpointer & Multi-turn (Pending)

No evidence yet. Tests to be added:
- Integration test: Same thread_id recovers prior messages
- E2E test: Cross-process thread recovery
- Security test: Cross-user thread isolation (403)
- Security test: Cross-tenant thread isolation (403)

## P0-03: Composition Root (Pending)

No evidence yet. Tests to be added:
- Integration test: All resources injected into AgentRuntime
- Integration test: Production mode fails fast on missing dependencies
- E2E test: Application shutdown closes all resources

## P0-04: HITL Graph Resume (Pending)

No evidence yet. Tests to be added:
- E2E test: Interrupt before tool execution, resume after approval
- E2E test: Model sees tool result and generates final answer
- Recovery test: Restart after interrupt, still able to approve and resume
- Security test: Duplicate approval doesn't re-execute
- Security test: Modified args after approval are rejected

## P0-05: Trusted Identity (Pending)

No evidence yet. Tests to be added:
- Security test: Model cannot override user_id via prompt
- Security test: Model cannot override approver identity
- Security test: Cross-account access denied
- Security test: Cross-tenant access denied

## P0-06: Tool Metadata (Pending)

No evidence yet. Tests to be added:
- Unit test: Tool with non-obvious name correctly classified
- Unit test: ToolDefinition provides correct Provider schema
- Integration test: New critical tool enters approval flow

## P0-07: Events/Metrics/Errors (Pending)

No evidence yet. Tests to be added:
- Unit test: Structured error codes map correctly
- Integration test: Per-step metrics recorded during run
- Integration test: Event store receives all lifecycle events
- Contract test: API returns machine-readable error codes

## P0-08: Type Check & Test Credibility (Pending)

No evidence yet. Tests to be added:
- Verify no mypy ignore_errors on critical modules
- README claims verified against test evidence
- Benchmark placeholder explicitly marked
