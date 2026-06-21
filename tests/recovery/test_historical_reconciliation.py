"""Historical reconciliation tests: empty tool_call_id → RECONCILIATION_REQUIRED.

These are behavioral executor tests — not DB-level or source-scan tests.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from fxfill_banking_agent.actor_resolver import FixedActorResolver
from fxfill_banking_agent.approval_executor import HITLApprovalExecutor
from fxfill_banking_agent.grant_repo import GrantRecord, GrantRepository, _digest
from fxfill_banking_agent.hitl_store import HITLSession, HITLSessionStatus, SqliteHITLStore
from fxfill_banking_agent.idempotency_store import SqliteIdempotencyStore
from fxfill_banking_agent.mcp_client import ToolCall, ToolResult
from fxfill_banking_agent.persistence import EventKind, SqliteEventStore


class CountingMCPClient:
    """MCP fake that counts calls — never actually dispatched for reconciliation."""

    def __init__(self) -> None:
        self.call_count = 0
        self.calls: list[ToolCall] = []

    @property
    def tools(self) -> dict:
        return {}

    async def connect(self) -> None:
        pass

    async def disconnect(self) -> None:
        pass

    async def call_tool(self, call: ToolCall) -> ToolResult:
        self.call_count += 1
        self.calls.append(call)
        return ToolResult(tool_name=call.name, success=True, content="ok")


class TestHistoricalEmptyToolCallID:
    """Real executor behavioral tests for historical records with tool_call_id==''."""

    @pytest.mark.asyncio
    async def test_executor_empty_tool_call_id_requires_reconciliation(
        self, tmp_path: Path
    ) -> None:
        """Executor returns reconciliation_required for empty tool_call_id."""
        db = tmp_path / "hist.db"
        now = datetime.now(timezone.utc).isoformat()

        # ── Setup: historical PENDING session with empty tool_call_id ──
        hitl = SqliteHITLStore(db)
        await hitl.insert(
            HITLSession(
                session_id="hist-1",
                user_id="u1",
                thread_id="t1",
                status=HITLSessionStatus.PENDING,
                tool_name="submit_transfer",
                tool_args={"amount": 100},
                tool_call_id="",  # ← historical record
                authorization_decision="PENDING",
                approval_requirement="required",
                idempotency_key="ik-hist-1",
                version=1,
                created_at=now,
                updated_at=now,
                expires_at=None,
            )
        )

        # ── Setup: corresponding durable grant with real tool_call_id ──
        grant_repo = GrantRepository(db)
        canonical = json.dumps({"amount": 100}, sort_keys=True)
        await grant_repo.insert_pending(
            GrantRecord(
                session_id="hist-1",
                requesting_user_id="u1",
                approving_actor_id="",
                thread_id="t1",
                run_id="hist-1",
                checkpoint_id="",
                tool_call_id="tc-real-1",
                tool_name="submit_transfer",
                canonical_tool_args=canonical,
                argument_digest=_digest({"amount": 100}),
                idempotency_key="ik-hist-1",
                decision="PENDING",
                status="PENDING",
                created_at=now,
                approved_at=None,
                expires_at=None,
                consuming_at=None,
                consumed_at=None,
                failed_at=None,
                version=1,
            )
        )

        # ── Real stores ──
        idem = SqliteIdempotencyStore(db)
        events = SqliteEventStore(db)
        await events.connect()
        mcp = CountingMCPClient()
        actor = FixedActorResolver("test-operator")

        executor = HITLApprovalExecutor(
            hitl_store=hitl,
            grant_repo=grant_repo,
            idempotency_store=idem,
            event_store=events,
            mcp_client=mcp,
            actor_resolver=actor,
        )

        # ── Execute ──
        result = await executor.approve("hist-1")

        # ── Assertions ──
        assert result.decision == "reconciliation_required"
        assert result.reconciliation_reason == "missing_historical_tool_call_id"
        assert "reconciliation" in (result.error or "").lower()

        # MCP was never called
        assert mcp.call_count == 0

        # Cleanup
        await events.close()

    @pytest.mark.asyncio
    async def test_empty_tool_call_id_produces_zero_mcp_calls(self, tmp_path: Path) -> None:
        """Zero MCP calls are dispatched for historical records."""
        db = tmp_path / "zero_mcp.db"
        now = datetime.now(timezone.utc).isoformat()

        hitl = SqliteHITLStore(db)
        await hitl.insert(
            HITLSession(
                session_id="zero-1",
                user_id="u1",
                thread_id="t1",
                status=HITLSessionStatus.PENDING,
                tool_name="transfer",
                tool_args={},
                tool_call_id="",
                authorization_decision="PENDING",
                approval_requirement="required",
                idempotency_key="ik-zero",
                version=1,
                created_at=now,
                updated_at=now,
                expires_at=None,
            )
        )

        grant_repo = GrantRepository(db)
        await grant_repo.insert_pending(
            GrantRecord(
                session_id="zero-1",
                requesting_user_id="u1",
                approving_actor_id="",
                thread_id="t1",
                run_id="zero-1",
                checkpoint_id="",
                tool_call_id="tc-zero",
                tool_name="transfer",
                canonical_tool_args="{}",
                argument_digest=_digest({}),
                idempotency_key="ik-zero",
                decision="PENDING",
                status="PENDING",
                created_at=now,
                approved_at=None,
                expires_at=None,
                consuming_at=None,
                consumed_at=None,
                failed_at=None,
                version=1,
            )
        )

        idem = SqliteIdempotencyStore(db)
        events = SqliteEventStore(db)
        await events.connect()
        mcp = CountingMCPClient()
        actor = FixedActorResolver()

        executor = HITLApprovalExecutor(
            hitl_store=hitl,
            grant_repo=grant_repo,
            idempotency_store=idem,
            event_store=events,
            mcp_client=mcp,
            actor_resolver=actor,
        )

        await executor.approve("zero-1")
        assert mcp.call_count == 0

        await events.close()

    @pytest.mark.asyncio
    async def test_reconciliation_state_persisted_in_hitl_and_grant(self, tmp_path: Path) -> None:
        """Both HITL session and grant expose RECONCILIATION_REQUIRED."""
        db = tmp_path / "persist.db"
        now = datetime.now(timezone.utc).isoformat()

        hitl = SqliteHITLStore(db)
        await hitl.insert(
            HITLSession(
                session_id="persist-1",
                user_id="u1",
                thread_id="t1",
                status=HITLSessionStatus.PENDING,
                tool_name="submit_transfer",
                tool_args={"amt": 50},
                tool_call_id="",
                authorization_decision="PENDING",
                approval_requirement="required",
                idempotency_key="ik-persist",
                version=1,
                created_at=now,
                updated_at=now,
                expires_at=None,
            )
        )

        grant_repo = GrantRepository(db)
        await grant_repo.insert_pending(
            GrantRecord(
                session_id="persist-1",
                requesting_user_id="u1",
                approving_actor_id="",
                thread_id="t1",
                run_id="persist-1",
                checkpoint_id="",
                tool_call_id="tc-persist",
                tool_name="submit_transfer",
                canonical_tool_args=json.dumps({"amt": 50}, sort_keys=True),
                argument_digest=_digest({"amt": 50}),
                idempotency_key="ik-persist",
                decision="PENDING",
                status="PENDING",
                created_at=now,
                approved_at=None,
                expires_at=None,
                consuming_at=None,
                consumed_at=None,
                failed_at=None,
                version=1,
            )
        )

        idem = SqliteIdempotencyStore(db)
        events = SqliteEventStore(db)
        await events.connect()
        mcp = CountingMCPClient()
        actor = FixedActorResolver()

        executor = HITLApprovalExecutor(
            hitl_store=hitl,
            grant_repo=grant_repo,
            idempotency_store=idem,
            event_store=events,
            mcp_client=mcp,
            actor_resolver=actor,
        )

        await executor.approve("persist-1")

        # HITL session is RECONCILIATION_REQUIRED
        session = await hitl.get("persist-1")
        assert session is not None
        assert session.status == HITLSessionStatus.RECONCILIATION_REQUIRED

        # Grant is RECONCILIATION_REQUIRED
        grant = await grant_repo.get_by_session("persist-1")
        assert grant is not None
        assert grant.status == "RECONCILIATION_REQUIRED"

        await events.close()

    @pytest.mark.asyncio
    async def test_reconciliation_event_is_queryable(self, tmp_path: Path) -> None:
        """A durable RECONCILIATION_REQUIRED event is persisted and queryable."""
        db = tmp_path / "event.db"
        now = datetime.now(timezone.utc).isoformat()

        hitl = SqliteHITLStore(db)
        await hitl.insert(
            HITLSession(
                session_id="event-1",
                user_id="u1",
                thread_id="t1",
                status=HITLSessionStatus.PENDING,
                tool_name="transfer",
                tool_args={},
                tool_call_id="",
                authorization_decision="PENDING",
                approval_requirement="required",
                idempotency_key="ik-event",
                version=1,
                created_at=now,
                updated_at=now,
                expires_at=None,
            )
        )

        grant_repo = GrantRepository(db)
        await grant_repo.insert_pending(
            GrantRecord(
                session_id="event-1",
                requesting_user_id="u1",
                approving_actor_id="",
                thread_id="t1",
                run_id="event-1",
                checkpoint_id="",
                tool_call_id="tc-event",
                tool_name="transfer",
                canonical_tool_args="{}",
                argument_digest=_digest({}),
                idempotency_key="ik-event",
                decision="PENDING",
                status="PENDING",
                created_at=now,
                approved_at=None,
                expires_at=None,
                consuming_at=None,
                consumed_at=None,
                failed_at=None,
                version=1,
            )
        )

        idem = SqliteIdempotencyStore(db)
        events = SqliteEventStore(db)
        await events.connect()
        mcp = CountingMCPClient()
        actor = FixedActorResolver()

        executor = HITLApprovalExecutor(
            hitl_store=hitl,
            grant_repo=grant_repo,
            idempotency_store=idem,
            event_store=events,
            mcp_client=mcp,
            actor_resolver=actor,
        )

        await executor.approve("event-1")

        # Query for RECONCILIATION_REQUIRED events
        rec_events = await events.query(kind=EventKind.RECONCILIATION_REQUIRED)
        assert len(rec_events) >= 1
        evt = rec_events[0]
        assert evt.kind == EventKind.RECONCILIATION_REQUIRED
        assert evt.payload.get("reason") == "missing_historical_tool_call_id"
        assert evt.payload.get("session_id") == "event-1"

        await events.close()

    @pytest.mark.asyncio
    async def test_grant_not_consumed_after_reconciliation(self, tmp_path: Path) -> None:
        """After reconciliation, grant status is not CONSUMED."""
        db = tmp_path / "not_consumed.db"
        now = datetime.now(timezone.utc).isoformat()

        hitl = SqliteHITLStore(db)
        await hitl.insert(
            HITLSession(
                session_id="nc-1",
                user_id="u1",
                thread_id="t1",
                status=HITLSessionStatus.PENDING,
                tool_name="transfer",
                tool_args={},
                tool_call_id="",
                authorization_decision="PENDING",
                approval_requirement="required",
                idempotency_key="ik-nc",
                version=1,
                created_at=now,
                updated_at=now,
                expires_at=None,
            )
        )

        grant_repo = GrantRepository(db)
        await grant_repo.insert_pending(
            GrantRecord(
                session_id="nc-1",
                requesting_user_id="u1",
                approving_actor_id="",
                thread_id="t1",
                run_id="nc-1",
                checkpoint_id="",
                tool_call_id="tc-nc",
                tool_name="transfer",
                canonical_tool_args="{}",
                argument_digest=_digest({}),
                idempotency_key="ik-nc",
                decision="PENDING",
                status="PENDING",
                created_at=now,
                approved_at=None,
                expires_at=None,
                consuming_at=None,
                consumed_at=None,
                failed_at=None,
                version=1,
            )
        )

        idem = SqliteIdempotencyStore(db)
        events = SqliteEventStore(db)
        await events.connect()
        mcp = CountingMCPClient()
        actor = FixedActorResolver()

        executor = HITLApprovalExecutor(
            hitl_store=hitl,
            grant_repo=grant_repo,
            idempotency_store=idem,
            event_store=events,
            mcp_client=mcp,
            actor_resolver=actor,
        )

        await executor.approve("nc-1")

        grant = await grant_repo.get_by_session("nc-1")
        assert grant is not None
        assert grant.status != "CONSUMED"
        assert grant.status == "RECONCILIATION_REQUIRED"

        await events.close()

    @pytest.mark.asyncio
    async def test_idempotency_not_succeeded_and_hitl_not_resumed(self, tmp_path: Path) -> None:
        """Idempotency is not SUCCEEDED and HITL is not RESUMED."""
        db = tmp_path / "not_terminal.db"
        now = datetime.now(timezone.utc).isoformat()

        hitl = SqliteHITLStore(db)
        await hitl.insert(
            HITLSession(
                session_id="nt-1",
                user_id="u1",
                thread_id="t1",
                status=HITLSessionStatus.PENDING,
                tool_name="transfer",
                tool_args={},
                tool_call_id="",
                authorization_decision="PENDING",
                approval_requirement="required",
                idempotency_key="ik-nt",
                version=1,
                created_at=now,
                updated_at=now,
                expires_at=None,
            )
        )

        grant_repo = GrantRepository(db)
        await grant_repo.insert_pending(
            GrantRecord(
                session_id="nt-1",
                requesting_user_id="u1",
                approving_actor_id="",
                thread_id="t1",
                run_id="nt-1",
                checkpoint_id="",
                tool_call_id="tc-nt",
                tool_name="transfer",
                canonical_tool_args="{}",
                argument_digest=_digest({}),
                idempotency_key="ik-nt",
                decision="PENDING",
                status="PENDING",
                created_at=now,
                approved_at=None,
                expires_at=None,
                consuming_at=None,
                consumed_at=None,
                failed_at=None,
                version=1,
            )
        )

        idem = SqliteIdempotencyStore(db)
        events = SqliteEventStore(db)
        await events.connect()
        mcp = CountingMCPClient()
        actor = FixedActorResolver()

        executor = HITLApprovalExecutor(
            hitl_store=hitl,
            grant_repo=grant_repo,
            idempotency_store=idem,
            event_store=events,
            mcp_client=mcp,
            actor_resolver=actor,
        )

        await executor.approve("nt-1")

        # HITL is NOT RESUMED
        session = await hitl.get("nt-1")
        assert session is not None
        assert session.status != HITLSessionStatus.RESUMED

        # Idempotency is NOT SUCCEEDED
        rec = await idem.get("ik-nt")
        # May be None (if reserve never called) or not SUCCEEDED
        if rec is not None:
            assert rec.status.value != "SUCCEEDED"

        await events.close()

    @pytest.mark.asyncio
    async def test_no_approval_granted_event_before_reconciliation(self, tmp_path: Path) -> None:
        """No APPROVAL_GRANTED event is emitted before reconciliation validation."""
        db = tmp_path / "no_approval.db"
        now = datetime.now(timezone.utc).isoformat()

        hitl = SqliteHITLStore(db)
        await hitl.insert(
            HITLSession(
                session_id="nag-1",
                user_id="u1",
                thread_id="t1",
                status=HITLSessionStatus.PENDING,
                tool_name="transfer",
                tool_args={},
                tool_call_id="",
                authorization_decision="PENDING",
                approval_requirement="required",
                idempotency_key="ik-nag",
                version=1,
                created_at=now,
                updated_at=now,
                expires_at=None,
            )
        )

        grant_repo = GrantRepository(db)
        await grant_repo.insert_pending(
            GrantRecord(
                session_id="nag-1",
                requesting_user_id="u1",
                approving_actor_id="",
                thread_id="t1",
                run_id="nag-1",
                checkpoint_id="",
                tool_call_id="tc-nag",
                tool_name="transfer",
                canonical_tool_args="{}",
                argument_digest=_digest({}),
                idempotency_key="ik-nag",
                decision="PENDING",
                status="PENDING",
                created_at=now,
                approved_at=None,
                expires_at=None,
                consuming_at=None,
                consumed_at=None,
                failed_at=None,
                version=1,
            )
        )

        idem = SqliteIdempotencyStore(db)
        events = SqliteEventStore(db)
        await events.connect()
        mcp = CountingMCPClient()
        actor = FixedActorResolver()

        executor = HITLApprovalExecutor(
            hitl_store=hitl,
            grant_repo=grant_repo,
            idempotency_store=idem,
            event_store=events,
            mcp_client=mcp,
            actor_resolver=actor,
        )

        await executor.approve("nag-1")

        # No APPROVAL_GRANTED checkpoint
        all_events = await events.query(kind=EventKind.CHECKPOINT)
        approval_granted = [e for e in all_events if e.payload.get("kind") == "APPROVAL_GRANTED"]
        assert len(approval_granted) == 0

        await events.close()
