# HITL Transfer Flow

## submit_transfer (HIGH_RISK)

1. User requests transfer via /agent
2. Agent creates transfer draft (REVERSIBLE_WRITE)
3. Agent attempts submit_transfer (HIGH_RISK)
4. AuthorizationGateway checks policy → PENDING
5. Graph raises RuntimeError → API returns 202
6. HITL session persisted to SqliteHITLStore
7. Human operator approves via POST /agent/approve
8. Approved session → AutoApprovePolicy for resume
9. New AgentRuntime executes only the pending tool call
10. Durable idempotency prevents double-execution
11. Result returned to user

## Rejection

1. POST /agent/approve with decision=reject
2. Session marked REJECTED (optimistic locking)
3. No banking side effects
4. Response: "Operation was rejected"

## Expiry

1. Session has expires_at timestamp
2. On approval attempt, expired sessions return 410
3. Session is marked EXPIRED

## Restart Safety

- All sessions in SQLite survive process restart
- Idempotency keys prevent duplicate transfers
- Optimistic locking prevents concurrent approve/reject
