# ADR 002: MCP Tool Boundaries

**Status:** Accepted  
**Date:** 2026-06-21

## Context

The banking agent must execute tools (account lookup, transaction search,
customer profile retrieval) on behalf of a simulated user. These tools
must be isolated from the agent's reasoning process — tool implementations
must not share memory, imports, or trust boundaries with LLM-generated
code or data.

## Decision

Expose all domain tools through **Model Context Protocol (MCP)** servers.

MCP provides:
- A standardized wire protocol for tool discovery and invocation;
- Process-level isolation between the agent runtime and tool
  implementations;
- Explicit, typed input/output schemas per tool;
- Server-authoritative access control.

Alternatives considered:

| Alternative | Rejected because |
|---|---|
| In-process Python functions | No isolation; tool code shares agent memory |
| HTTP REST services | Requires per-tool endpoint management and auth plumbing |
| gRPC services | Heavier protocol; MCP is purpose-built for LLM tool use |

## Consequences

- Each tool domain (e.g., banking core) runs as a separate MCP server
  process.
- Tool schemas are validated at the MCP boundary before reaching the agent.
- The agent runtime is an MCP client; it never imports tool code directly.
- Adding a new tool means adding it to the relevant MCP server — no agent
  code changes needed.
