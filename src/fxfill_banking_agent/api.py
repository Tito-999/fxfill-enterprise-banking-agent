"""FastAPI service wrapping the banking agent with durable HITL persistence."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from fxfill_banking_agent.agent import AgentRuntime
from fxfill_banking_agent.approval_executor import ApprovalResult, HITLApprovalExecutor
from fxfill_banking_agent.auth import (
    ApprovalDecision,
    AuthorizationGateway,
    Operation,
    OperationKind,
)
from fxfill_banking_agent.config import AgentConfig
from fxfill_banking_agent.grant_repo import GrantRepository, _digest
from fxfill_banking_agent.hitl_signal import HITLPending
from fxfill_banking_agent.hitl_store import HITLSession, HITLSessionStatus, SqliteHITLStore
from fxfill_banking_agent.llm import LLMProvider
from fxfill_banking_agent.mcp_client import MCPClient

# ── Schemas ──────────────────────────────────────────────────────────


class AgentRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=10000)
    session_id: str | None = Field(None)


class AgentResponse(BaseModel):
    session_id: str
    answer: str | None
    step_count: int
    status: str = "complete"


class ApprovalRequest(BaseModel):
    session_id: str = Field(..., min_length=1)
    decision: str = Field(..., pattern="^(approve|reject)$")
    approver: str = Field("human-operator")


class ApprovalResponse(BaseModel):
    session_id: str
    decision: str
    result: dict[str, Any] | None = None


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str


# ── Application factory ──────────────────────────────────────────────


def create_app(
    llm: LLMProvider,
    mcp_client: MCPClient,
    config: AgentConfig | None = None,
    auth_gateway: AuthorizationGateway | None = None,
    hitl_store: SqliteHITLStore | None = None,
    grant_repo: "GrantRepository | None" = None,
    approval_executor: "HITLApprovalExecutor | None" = None,
) -> FastAPI:
    """Create the FastAPI application.

    Args:
        llm: LLM provider.
        mcp_client: MCP client.
        config: Agent configuration override.
        auth_gateway: Authorization gateway.
        hitl_store: HITL session store.
        grant_repo: Grant repository.
        approval_executor: HITL approval executor (preferred over manual deps).

    Raises:
        RuntimeError: If auth_gateway is missing or HITL is enabled
            without required durable dependencies.
    """
    agent_cfg = config or AgentConfig()
    if auth_gateway is None:
        raise RuntimeError(
            "create_app requires an explicit AuthorizationGateway — refusing to fail open"
        )
    gateway = auth_gateway

    # Durable HITL store: use provided or create from config
    if hitl_store is not None:
        _hitl = hitl_store
    elif agent_cfg.persistence.db_path:
        _hitl = SqliteHITLStore(
            agent_cfg.persistence.db_path,
            expiry_minutes=agent_cfg.persistence.hitl_expiry_minutes,
        )
    else:
        _hitl = None

    runtime = AgentRuntime(
        config=agent_cfg,
        llm=llm,
        mcp_client=mcp_client,
        auth_gateway=gateway,
    )

    app = FastAPI(
        title="fxfill-enterprise-banking-agent",
        version="0.1.0",
    )

    @app.get("/health", response_model=HealthResponse)
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": "0.1.0"}

    @app.post("/agent", response_model=AgentResponse)
    async def agent_endpoint(request: AgentRequest) -> dict[str, Any]:
        op = Operation(
            kind=OperationKind.READ,
            name="agent_request",
            target=f"session:{request.session_id or 'new'}",
            details={"message": request.message},
        )
        decision = await gateway.authorize(op)

        if decision.decision == ApprovalDecision.DENIED:
            raise HTTPException(status_code=403, detail="Request denied by authorization policy")

        if decision.decision == ApprovalDecision.PENDING:
            raise HTTPException(status_code=401, detail="Request requires human approval")

        try:
            result = await runtime.run(request.message, run_id=request.session_id)
        except HITLPending as pause:
            # Typed HITL pause — store structured details + grant, return 202

            session_id = request.session_id or pause.session_id or "unknown"
            now = datetime.now(timezone.utc).isoformat()
            canonical_args = json.dumps(pause.tool_args, sort_keys=True)
            arg_digest = _digest(pause.tool_args)
            idem_key = pause.idempotency_key or f"{session_id}:{pause.tool_call_id}"

            if _hitl is not None:
                hitl_session = HITLSession(
                    session_id=session_id,
                    user_id="default",
                    thread_id=pause.thread_id or session_id,
                    status=HITLSessionStatus.PENDING,
                    tool_name=pause.tool_name,
                    tool_args=pause.tool_args,
                    tool_call_id=pause.tool_call_id,
                    authorization_decision="PENDING",
                    approval_requirement="required",
                    idempotency_key=idem_key,
                    version=1,
                    created_at=now,
                    updated_at=now,
                    expires_at=None,
                )
                await _hitl.insert(hitl_session)

            if grant_repo is not None:
                from fxfill_banking_agent.grant_repo import GrantRecord

                grant = GrantRecord(
                    session_id=session_id,
                    requesting_user_id="default",
                    approving_actor_id="",
                    thread_id=pause.thread_id or session_id,
                    run_id=session_id,
                    checkpoint_id="",
                    tool_call_id=pause.tool_call_id,
                    tool_name=pause.tool_name,
                    canonical_tool_args=canonical_args,
                    argument_digest=arg_digest,
                    idempotency_key=idem_key,
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
                await grant_repo.insert_pending(grant)

            raise HTTPException(
                status_code=202,
                detail=f"Action requires approval. Use POST /agent/approve with session_id={session_id}",
            ) from pause
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        return {
            "session_id": result.get("session_id", ""),
            "answer": result.get("final_answer"),
            "step_count": result.get("step_count", 0),
            "status": "complete",
        }

    @app.post("/agent/approve", response_model=ApprovalResponse)
    async def approve_endpoint(request: ApprovalRequest) -> dict[str, Any]:
        # request.approver is an untrusted note; never used for authorization
        if approval_executor is None:
            raise HTTPException(status_code=501, detail="HITL approval executor not configured")
        context = None
        if request.decision == "reject":
            result = await approval_executor.reject(request.session_id, context)
        else:
            result = await approval_executor.approve(request.session_id, context)
        _map_executor_result(result)
        return {
            "session_id": result.session_id,
            "decision": result.decision,
            "result": {"answer": result.answer, "step_count": result.step_count}
            if result.answer
            else None,
        }

    def _map_executor_result(result: ApprovalResult) -> None:
        if result.error:
            status_code = 409 if "Already" in (result.error or "") else 500
            raise HTTPException(status_code=status_code, detail=result.error)

    return app
