# Architecture Decisions — FxFill Enterprise Banking Agent

**Started:** 2026-06-24

## DECISION-001: P0 Implementation Order

**Date:** 2026-06-24
**Decision:** Implement P0 in strict numerical order: P0-01 → P0-02 → P0-03 → P0-04 → P0-05 → P0-06 → P0-07 → P0-08

**Rationale:**
- P0-01 (Function Calling) must come first — all other work depends on the model being able to receive tools and produce tool calls
- P0-02 (Checkpointer) depends on P0-01 being correct, since checkpointing must save/restore tool call state
- P0-03 (Composition Root) wires all dependencies; must be done after P0-02 to ensure checkpointer is injected
- P0-04 (HITL Resume) depends on checkpointer working (P0-02) and composition root (P0-03)
- P0-05 (Identity) can be done in parallel with P0-06 (Metadata) after P0-04
- P0-07 (Events/Metrics) depends on the main chain being wired
- P0-08 (Cleanup) must be done last to capture all changes

**Rejected alternatives:**
- Parallel P0-01 and P0-02: Function Calling changes affect the graph structure that P0-02 modifies
- Starting with P0-08 (types): Would require re-typing code that hasn't been stabilized yet

## DECISION-002: Provider Adapter Architecture

**Date:** 2026-06-24
**Decision:** Create separate adapter classes for OpenAI-compatible and Anthropic-compatible protocols rather than mixing formats in a single provider.

**Rationale:**
- Current DeepSeekProvider mixes Anthropic request format with OpenAI response parsing
- Separate adapters make protocol boundaries explicit
- A base adapter handles message conversion; protocol adapters handle tool format differences
- Tests can verify each protocol independently

## DECISION-003: HITL Resume Pattern

**Date:** 2026-06-24
**Decision:** Use LangGraph `interrupt()` / `Command(resume=...)` pattern for HITL instead of the current bypass-executor approach.

**Rationale:**
- Current approach executes tools outside the graph — model never sees results
- LangGraph's built-in interrupt/resume preserves graph state and allows model to continue reasoning
- Aligns with LangGraph's intended usage patterns
- Enables proper tool result feedback into the conversation

## DECISION-004: Tool Metadata Schema

**Date:** 2026-06-24
**Decision:** Introduce `ToolDefinition` as the single source of truth for tool metadata (side_effect, risk_level, permissions, approval_policy) and generate both AuthorizationPolicy input and Provider tool schema from it.

**Rationale:**
- Eliminates substring-based risk classification
- Single registry ensures authorization and Provider schema stay in sync
- Adding a new tool requires explicit metadata, preventing accidental misclassification

## DECISION-005: TrustedRequestContext

**Date:** 2026-06-24
**Decision:** Create an immutable `TrustedRequestContext` populated by authentication middleware. Tool execution must receive context injection, not read identity from model-generated args.

**Rationale:**
- Currently user_id is hardcoded and approver comes from HTTP body
- Immutable context prevents accidental mutation
- Server-side injection means model cannot forge identity

## DECISION-006: Open Commit Questions

- Whether to use `interrupt()` (LangGraph 0.2+) or manual checkpoint management for HITL
- Whether to adopt LangGraph's built-in `ToolNode` or keep custom `_tool_node`
- Exact ToolDefinition schema fields (how detailed should permissions be?)
