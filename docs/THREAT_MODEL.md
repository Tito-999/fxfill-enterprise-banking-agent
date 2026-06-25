# Threat Model

## Attack Surfaces

| Surface | Risk | Mitigation |
|---|---|---|
| Direct prompt injection | Critical | Deterministic auth gate, tool allowlist, identity injection |
| Indirect RAG injection | High | Document text as untrusted, never overrides system policy |
| Privilege escalation | Critical | RBAC + ABAC, roles from verified tokens only |
| Cross-tenant access | Critical | Tenant scope on all queries, middleware enforcement |
| Token replay | High | jti validation, short-lived tokens, rate limiting |
| Approval bypass | Critical | Exact-operation grant, single-use, identity binding |
| Data exfiltration | Medium | Tool allowlist, no arbitrary code execution |
| Denial-of-wallet | Medium | Token budgets, step limits, rate limiting |
| Secret leakage | Critical | PII redaction in logs, no tokens in traces |

## Security Invariants

1. user_id comes from verified tokens, never from LLM/prompt/body
2. approver identity comes from auth middleware, never from HTTP body
3. Side-effecting tools go through: validate → auth → HITL → execute
4. idempotency keys prevent duplicate execution
5. UNKNOWN outcomes never auto-retry
6. Production rejects dev headers, SQLite, CORS wildcard
