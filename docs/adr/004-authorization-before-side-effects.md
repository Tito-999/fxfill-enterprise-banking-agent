# ADR 004: Authorization Before Side Effects

**Status:** Accepted  
**Date:** 2026-06-21

## Context

Banking operations (transfers, profile updates, statement generation)
are side-effecting. In a production system, these would require
explicit authorization. The agent architecture must model this so
that human approval can be inserted without architectural changes.

## Decision

**Separate authorization from side-effecting tool execution.**

Every side-effecting operation passes through a three-phase pipeline:

1. **Intent**: The agent decides what to do (LLM-produced).
2. **Authorization gate**: A deterministic check — in development
   this may auto-approve; in production it requires human sign-off.
3. **Execution**: The authorized operation is dispatched to the
   appropriate MCP server.

The authorization gate is an explicit interface:

```python
class AuthorizationGateway(Protocol):
    async def authorize(
        self, operation: Operation, context: AgentContext
    ) -> AuthorizationDecision: ...
```

Alternatives considered:

| Alternative | Rejected because |
|---|---|
| Authorize inside tool code | Authorization policy mixed with business logic |
| Prompt the LLM to check permissions | Not a security boundary |
| Separate auth service + message queue | Over-engineered for Phase 0–2; can adopt later |

## Consequences

- Every side-effecting tool is wrapped with an authorization check.
- The human approval workflow (Phase 3) plugs into the existing gate.
- Authorization decisions are logged and auditable.
- Read operations may skip the authorization gate if the policy allows.
