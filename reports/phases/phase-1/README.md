# Phase 1 — LangGraph Agent Scaffolding

**Status:** COMPLETE
**Date:** 2026-06-21

## Exit Criteria

| Criterion | Status | Detail |
|---|---|---|
| Agent graph compiles | ✅ PASS | `build_agent_graph()` returns compiled StateGraph |
| Graph topology correct | ✅ PASS | agent_node → tool_node → agent_node loop |
| Mock LLM works | ✅ PASS | MockLLM and EchoLLM tested |
| MCP client stub works | ✅ PASS | StubMCPClient with queued responses |
| Unit tests pass | ✅ PASS | 66 total (38 Phase 0 + 28 Phase 1) |
| Ruff passes | ✅ PASS | All checks passed |
| Mypy strict | ✅ PASS | No issues in 8 source files |
| No real LLM calls | ✅ PASS | Only mock/stub implementations |
| No benchmark access | ✅ PASS | No imports from tau2 evaluator |

## New Files

| File | Purpose |
|---|---|
| `src/fxfill_banking_agent/state.py` | AgentState TypedDict |
| `src/fxfill_banking_agent/llm.py` | LLMProvider protocol + MockLLM + EchoLLM |
| `src/fxfill_banking_agent/mcp_client.py` | MCPClient protocol + StubMCPClient |
| `src/fxfill_banking_agent/graph.py` | LangGraph state graph (agent + tool nodes) |
| `tests/unit/test_llm.py` | 6 tests |
| `tests/unit/test_mcp_client.py` | 7 tests |
| `tests/unit/test_graph.py` | 15 tests (topology, nodes, routing, e2e) |

## Dependencies Added

- `langgraph>=0.4,<1.0` (0.6.11 installed)
- `langchain-core>=0.3,<1.0` (0.3.86 installed)
- `pytest-asyncio>=1.4.0` (dev)
