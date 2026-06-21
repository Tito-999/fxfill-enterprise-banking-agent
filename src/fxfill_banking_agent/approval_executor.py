"""HITL approval executor — owns the complete approval workflow."""

from __future__ import annotations

import json
from dataclasses import dataclass

from fxfill_banking_agent.actor_resolver import ApprovalActorResolver
from fxfill_banking_agent.grant_repo import GrantRepository
from fxfill_banking_agent.hitl_store import HITLSessionStatus, SqliteHITLStore
from fxfill_banking_agent.idempotency_store import SqliteIdempotencyStore
from fxfill_banking_agent.logging import get_logger
from fxfill_banking_agent.mcp_client import MCPClient
from fxfill_banking_agent.persistence import AgentEvent, EventKind, EventStore

logger = get_logger(__name__)


@dataclass
class ApprovalResult:
    decision: str  # "approved", "rejected"
    session_id: str
    answer: str | None = None
    step_count: int = 0
    error: str | None = None


class HITLApprovalExecutor:
    """Owns the complete HITL approval workflow.

    The FastAPI endpoint delegates to this executor for all approval
    and rejection logic, keeping the endpoint thin.
    """

    def __init__(
        self,
        *,
        hitl_store: SqliteHITLStore,
        grant_repo: GrantRepository,
        idempotency_store: SqliteIdempotencyStore,
        event_store: EventStore,
        mcp_client: MCPClient,
        actor_resolver: ApprovalActorResolver,
    ) -> None:
        self._hitl = hitl_store
        self._grant = grant_repo
        self._idem = idempotency_store
        self._events = event_store
        self._mcp = mcp_client
        self._actor = actor_resolver

    async def _persist_event(self, run_id: str, seq: int, kind: EventKind, payload: dict) -> None:
        try:
            await self._events.insert(
                AgentEvent(run_id=run_id, seq=seq, kind=kind, payload=payload)
            )
        except Exception:
            logger.warning("event_persist_failed", run_id=run_id, kind=kind.value)

    async def approve(self, session_id: str, request_context: dict | None = None) -> ApprovalResult:
        """Execute the full HITL approval workflow.

        1. Resolve trusted actor
        2. Load and validate HITL session
        3. Approve grant (PENDING→APPROVED)
        4. Atomic claim (APPROVED→CONSUMING)
        5. Durable idempotency check
        6. Exact MCP execution
        7. Mark terminal state
        8. Persist events
        """
        session = await self._hitl.get(session_id)
        if session is None:
            return ApprovalResult("error", session_id, error="Session not found")

        if session.is_terminal():
            return ApprovalResult("error", session_id, error=f"Already {session.status.value}")

        if session.is_expired():
            await self._hitl.update_status(
                session_id, HITLSessionStatus.EXPIRED, expected_version=session.version
            )
            return ApprovalResult("error", session_id, error="Session expired")

        # Resolve trusted actor
        actor = self._actor.resolve(request_context)
        if actor is None:
            return ApprovalResult("error", session_id, error="Trusted actor identity required")

        # Approve grant
        if not await self._grant.approve_pending(session_id, actor.actor_id, expected_version=1):
            return ApprovalResult("error", session_id, error="Grant approval failed")

        # Approve HITL session
        if not await self._hitl.update_status(
            session_id, HITLSessionStatus.APPROVED, expected_version=session.version
        ):
            return ApprovalResult("error", session_id, error="Session update failed")

        await self._persist_event(
            session_id,
            0,
            EventKind.CHECKPOINT,
            {"kind": "APPROVAL_GRANTED", "actor": actor.actor_id},
        )

        # Atomic claim
        claimed = await self._grant.atomic_consume(
            session_id=session_id,
            user_id=session.user_id,
            approving_actor_id=actor.actor_id,
            thread_id=session.thread_id,
            run_id=session_id,
            tool_call_id=session.tool_call_id,
            tool_name=session.tool_name,
            tool_args=session.tool_args,
            idempotency_key=session.idempotency_key or "",
            version=1,
        )
        if claimed is None:
            return ApprovalResult("error", session_id, error="Grant already consumed")

        await self._persist_event(session_id, 1, EventKind.CHECKPOINT, {"kind": "GRANT_CLAIMED"})

        # Durable idempotency: reserve or check before dispatch
        idem_key = session.idempotency_key or session_id
        existing = await self._idem.get(idem_key)
        if existing is not None:
            if existing.status.value == "SUCCEEDED":
                return ApprovalResult("approved", session_id, answer=existing.result or "done")
            if existing.status.value in ("RESERVED", "EXECUTING", "UNKNOWN"):
                await self._grant.mark_failed(session_id)
                await self._hitl.update_status(
                    session_id, HITLSessionStatus.FAILED, expected_version=session.version + 1
                )
                await self._persist_event(
                    session_id, 2, EventKind.CHECKPOINT, {"kind": "REPLAY_DENIED"}
                )
                return ApprovalResult(
                    "error", session_id, error=f"Idempotency {existing.status.value} — fails closed"
                )

        # Reserve idempotency key
        await self._idem.reserve(idem_key, session.tool_name, session.tool_args)

        # Execute exact MCP tool call from canonical args
        exec_args = json.loads(claimed.canonical_tool_args)
        from fxfill_banking_agent.mcp_client import ToolCall

        tool_call = ToolCall(name=claimed.tool_name, arguments=exec_args)

        await self._persist_event(
            session_id, 3, EventKind.CHECKPOINT, {"kind": "MCP_DISPATCH_STARTED"}
        )

        try:
            mcp_result = await self._mcp.call_tool(tool_call)
        except Exception:
            await self._idem.mark_unknown(idem_key)
            await self._grant.mark_unknown(session_id)
            await self._hitl.update_status(
                session_id, HITLSessionStatus.FAILED, expected_version=session.version + 1
            )
            await self._persist_event(
                session_id, 4, EventKind.CHECKPOINT, {"kind": "MCP_EXECUTION_UNKNOWN"}
            )
            return ApprovalResult(
                "error", session_id, error="MCP dispatch failed — outcome unknown"
            )

        if mcp_result.success:
            await self._idem.mark_succeeded(idem_key, mcp_result.content)
            await self._grant.mark_consumed(session_id)
            await self._hitl.update_status(
                session_id, HITLSessionStatus.RESUMED, expected_version=session.version + 1
            )
            await self._persist_event(
                session_id, 4, EventKind.CHECKPOINT, {"kind": "MCP_EXECUTION_SUCCEEDED"}
            )
            return ApprovalResult("approved", session_id, answer=mcp_result.content)

        await self._idem.mark_failed(idem_key, mcp_result.error or "unknown")
        await self._grant.mark_failed(session_id)
        await self._hitl.update_status(
            session_id, HITLSessionStatus.FAILED, expected_version=session.version + 1
        )
        await self._persist_event(
            session_id, 4, EventKind.CHECKPOINT, {"kind": "MCP_EXECUTION_FAILED"}
        )
        return ApprovalResult("error", session_id, error=f"MCP failed: {mcp_result.error}")

    async def reject(self, session_id: str, request_context: dict | None = None) -> ApprovalResult:
        """Reject a pending HITL session."""
        session = await self._hitl.get(session_id)
        if session is None:
            return ApprovalResult("error", session_id, error="Session not found")

        if session.is_terminal():
            return ApprovalResult("error", session_id, error=f"Already {session.status.value}")

        actor = self._actor.resolve(request_context)
        if actor is None:
            return ApprovalResult("error", session_id, error="Trusted actor identity required")

        if not await self._hitl.update_status(
            session_id, HITLSessionStatus.REJECTED, expected_version=session.version
        ):
            return ApprovalResult("error", session_id, error="Session update failed")

        await self._grant.mark_rejected(session_id)
        await self._persist_event(
            session_id,
            0,
            EventKind.CHECKPOINT,
            {"kind": "APPROVAL_REJECTED", "actor": actor.actor_id},
        )

        return ApprovalResult(
            "rejected", session_id, answer="Operation was rejected by human operator."
        )
