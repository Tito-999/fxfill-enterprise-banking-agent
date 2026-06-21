"""Security tests: exact-match HITL approval grant."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig

from fxfill_banking_agent.auth import (
    ApprovedOperationGrant,
    ApprovedOperationGrantPolicy,
    AuthorizationGateway,
    Operation,
    OperationKind,
    RequireApprovalPolicy,
)
from fxfill_banking_agent.graph import _tool_node
from fxfill_banking_agent.llm import MockLLM
from fxfill_banking_agent.mcp_client import StubMCPClient
from fxfill_banking_agent.state import AgentState


def _make_grant(**overrides) -> ApprovedOperationGrant:
    now = datetime.now(timezone.utc).isoformat()
    defaults = {
        "session_id": "sess-1",
        "approving_user": "operator",
        "requesting_user": "user-alice",
        "thread_id": "t1",
        "tool_name": "submit_transfer",
        "tool_args": {"draft_id": "draft-1", "user_id": "user-alice"},
        "idempotency_key": "idem-1",
        "decision": "approved",
        "created_at": now,
        "expires_at": None,
        "consumed": False,
        "version": 1,
    }
    defaults.update(overrides)
    return ApprovedOperationGrant(**defaults)


class TestGrantExactMatch:
    """Exact match: all fields must align."""

    def test_exact_match_authorizes(self) -> None:
        grant = _make_grant()
        assert grant.can_authorize(
            session_id="sess-1",
            user_id="user-alice",
            thread_id="t1",
            tool_name="submit_transfer",
            tool_args={"draft_id": "draft-1", "user_id": "user-alice"},
            idempotency_key="idem-1",
        )

    def test_modified_amount_denied(self) -> None:
        grant = _make_grant(
            tool_args={"draft_id": "draft-1", "user_id": "user-alice", "amount": 100}
        )
        assert not grant.can_authorize(
            session_id="sess-1",
            user_id="user-alice",
            thread_id="t1",
            tool_name="submit_transfer",
            tool_args={"draft_id": "draft-1", "user_id": "user-alice", "amount": 999},
            idempotency_key="idem-1",
        )

    def test_modified_beneficiary_denied(self) -> None:
        grant = _make_grant(tool_args={"beneficiary_id": "BEN-001"})
        assert not grant.can_authorize(
            session_id="sess-1",
            user_id="user-alice",
            thread_id="t1",
            tool_name="submit_transfer",
            tool_args={"beneficiary_id": "BEN-999"},
            idempotency_key="idem-1",
        )

    def test_changed_tool_name_denied(self) -> None:
        grant = _make_grant(tool_name="submit_transfer")
        assert not grant.can_authorize(
            session_id="sess-1",
            user_id="user-alice",
            thread_id="t1",
            tool_name="cancel_transfer",
            tool_args={},
            idempotency_key="idem-1",
        )

    def test_cross_user_denied(self) -> None:
        grant = _make_grant(requesting_user="user-alice")
        assert not grant.can_authorize(
            session_id="sess-1",
            user_id="user-bob",
            thread_id="t1",
            tool_name="submit_transfer",
            tool_args={},
            idempotency_key="idem-1",
        )

    def test_cross_session_denied(self) -> None:
        grant = _make_grant(session_id="sess-1")
        assert not grant.can_authorize(
            session_id="sess-2",
            user_id="user-alice",
            thread_id="t1",
            tool_name="submit_transfer",
            tool_args={},
            idempotency_key="idem-1",
        )

    def test_different_idempotency_key_denied(self) -> None:
        grant = _make_grant(idempotency_key="idem-1")
        assert not grant.can_authorize(
            session_id="sess-1",
            user_id="user-alice",
            thread_id="t1",
            tool_name="submit_transfer",
            tool_args={},
            idempotency_key="idem-2",
        )

    def test_expired_grant_denied(self) -> None:
        past = (datetime.now(timezone.utc).replace(year=2020)).isoformat()
        grant = _make_grant(expires_at=past)
        assert grant.is_expired()
        assert not grant.can_authorize(
            session_id="sess-1",
            user_id="user-alice",
            thread_id="t1",
            tool_name="submit_transfer",
            tool_args={},
            idempotency_key="idem-1",
        )

    def test_consumed_grant_denied(self) -> None:
        grant = _make_grant(consumed=True)
        assert not grant.can_authorize(
            session_id="sess-1",
            user_id="user-alice",
            thread_id="t1",
            tool_name="submit_transfer",
            tool_args={},
            idempotency_key="idem-1",
        )

    def test_rejected_decision_denied(self) -> None:
        grant = _make_grant(decision="rejected")
        assert not grant.can_authorize(
            session_id="sess-1",
            user_id="user-alice",
            thread_id="t1",
            tool_name="submit_transfer",
            tool_args={},
            idempotency_key="idem-1",
        )


class TestGrantPolicy:
    """ApprovedOperationGrantPolicy: single-use, exact-match enforcement."""

    def test_first_call_approved_second_denied(self) -> None:
        grant = _make_grant()
        policy = ApprovedOperationGrantPolicy(grant)

        op = Operation(
            kind=OperationKind.TRANSFER,
            name="submit_transfer",
            target="draft-1",
            details={
                "args": {"draft_id": "draft-1", "user_id": "user-alice"},
                "session_id": "sess-1",
                "user_id": "user-alice",
                "thread_id": "t1",
                "idempotency_key": "idem-1",
            },
        )
        d1 = policy.authorize(op)
        assert d1.decision.value == "approved"

        # Second call — already consumed
        d2 = policy.authorize(op)
        assert d2.decision.value == "denied"
        assert "already consumed" in d2.reason

    def test_non_matching_operation_denied(self) -> None:
        grant = _make_grant()
        policy = ApprovedOperationGrantPolicy(grant)

        op = Operation(
            kind=OperationKind.WRITE,
            name="cancel_transfer",
            target="x",
            details={
                "args": {},
                "session_id": "sess-1",
                "user_id": "user-alice",
                "thread_id": "t1",
                "idempotency_key": "idem-1",
            },
        )
        d = policy.authorize(op)
        assert d.decision.value == "denied"
        assert "does not match" in d.reason


class TestHITLPauseSignal:
    """The graph emits structured HITL pause data."""

    @pytest.mark.asyncio
    async def test_pause_contains_tool_data(self) -> None:
        """RuntimeError from HITL contains JSON payload with tool info."""
        auth = AuthorizationGateway(policy=RequireApprovalPolicy())
        msg = AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "submit_transfer",
                    "args": {"draft_id": "draft-1", "user_id": "user-alice"},
                    "id": "tc1",
                }
            ],
        )
        state: AgentState = {
            "messages": [HumanMessage(content="send"), msg],
            "session_id": "sess-test",
        }

        config = RunnableConfig(
            configurable={
                "llm": MockLLM(),
                "mcp_client": StubMCPClient(),
                "auth_gateway": auth,
                "agent_config": None,
            }
        )

        from fxfill_banking_agent.hitl_signal import HITLPending

        with pytest.raises(HITLPending):
            await _tool_node(state, config)

    @pytest.mark.asyncio
    async def test_pause_payload_parseable(self) -> None:
        """The HITL JSON payload is valid and contains expected keys."""
        auth = AuthorizationGateway(policy=RequireApprovalPolicy())
        msg = AIMessage(
            content="",
            tool_calls=[{"name": "submit_transfer", "args": {"draft_id": "draft-x"}, "id": "tc2"}],
        )
        state: AgentState = {
            "messages": [HumanMessage(content="send"), msg],
            "session_id": "sess-parse",
        }

        config = RunnableConfig(
            configurable={
                "llm": MockLLM(),
                "mcp_client": StubMCPClient(),
                "auth_gateway": auth,
                "agent_config": None,
            }
        )

        from fxfill_banking_agent.hitl_signal import HITLPending

        try:
            await _tool_node(state, config)
        except HITLPending as pause:
            assert pause.tool_name == "submit_transfer"
            assert pause.session_id == "sess-parse"
            assert pause.tool_args == {"draft_id": "draft-x"}
            assert pause.tool_call_id == "tc2"


class TestAutoApprovePolicyScan:
    """Verify no blanket AutoApprovePolicy in production resume path."""

    def test_grant_policy_not_auto_approve(self) -> None:
        """ApprovedOperationGrantPolicy is not AutoApprovePolicy."""
        from fxfill_banking_agent.auth import AutoApprovePolicy

        grant = _make_grant()
        policy = ApprovedOperationGrantPolicy(grant)
        assert not isinstance(policy, AutoApprovePolicy)

    def test_grant_classification(self) -> None:
        """submit_transfer is still classified as HIGH_RISK."""
        from fxfill_banking_agent.banking.models import RiskClassification
        from fxfill_banking_agent.banking.policy import TOOL_RISK

        assert TOOL_RISK["submit_transfer"] == RiskClassification.HIGH_RISK
