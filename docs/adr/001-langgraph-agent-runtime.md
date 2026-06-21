# ADR 001: LangGraph Agent Runtime

**Status:** Accepted  
**Date:** 2026-06-21

## Context

The banking agent needs a deterministic, observable runtime that composes LLM
reasoning steps with structured tool calls. The runtime must support
interruptible execution, human-in-the-loop approval, and per-step
observability.

## Decision

Use **LangGraph** as the agent runtime framework.

LangGraph provides:
- Directed graph execution with typed state;
- Checkpointing and interrupt/resume semantics;
- Built-in support for tool-calling agent patterns;
- Integration with LangChain's model abstraction (`langchain-core` / `langchain-openai`).

Alternatives considered:

| Alternative | Rejected because |
|---|---|
| Raw asyncio state machine | Rebuilds checkpointing, interrupts, and graph visualization |
| AutoGen | Less mature interrupt/resume model at decision time |
| CrewAI | Multi-agent focus; heavier than needed for single-agent banking domain |

## Consequences

- Runtime code depends on `langgraph` and `langchain-core`.
- Agent state is typed and checkpointed at every step.
- Human approval is modeled as a graph interrupt.
- The graph definition (nodes, edges, conditional routing) is the
  single source of truth for agent behavior.
