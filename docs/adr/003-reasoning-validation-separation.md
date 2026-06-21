# ADR 003: Reasoning–Validation Separation

**Status:** Accepted  
**Date:** 2026-06-21

## Context

LLM outputs are probabilistic and must not be trusted as the final
authority for business rules, security checks, or data integrity.
The agent architecture must ensure that LLM reasoning and
deterministic validation are distinct, auditable concerns.

## Decision

**Separate LLM reasoning from deterministic validation.**

- **LLM reasoning** produces intents: which tool to call, what arguments
  to pass, how to interpret retrieved documents.
- **Deterministic validators** (pure Python functions) enforce:
  - Tool argument schemas (type, range, required fields);
  - Authorization rules (is this operation allowed?);
  - Business invariants (e.g., transaction amount limits);
  - Output sanitization before returning to the user.

This follows the **tofu** principle: Trust Nothing From the LLM
Without Explicit Validation. Every LLM output that reaches a
side-effecting path must pass through a validator.

Alternatives considered:

| Alternative | Rejected because |
|---|---|
| Prompt-only guardrails | Prompt instructions are not an authorization boundary |
| LLM-as-judge validation | Circular: uses an LLM to validate LLM output |
| Mixed reasoning+validation in one function | Not auditable; cannot prove which logic ran |

## Consequences

- Every tool-call path has an explicit `validate_*` function.
- Validators are unit-testable without an LLM.
- Audit logs distinguish "LLM chose action X" from "validator approved/rejected X".
- The pattern adds boilerplate per-tool; this is intentional and
  accepted as a security property.
