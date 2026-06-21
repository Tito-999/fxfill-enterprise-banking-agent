"""FastAPI service wrapping the banking agent with durable HITL persistence."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from fxfill_banking_agent.agent import AgentRuntime
from fxfill_banking_agent.auth import (
    ApprovalDecision,
    AuthorizationGateway,
    AutoApprovePolicy,
    Operation,
    OperationKind,
)
from fxfill_banking_agent.config import AgentConfig
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
) -> FastAPI:
    """Create the FastAPI application with durable HITL store.

    Args:
        llm: LLM provider (must be configured — mocks not accepted in production).
        mcp_client: MCP client.
        config: Agent configuration override.
        auth_gateway: Authorization gateway (defaults to auto-approve).
        hitl_store: HITL session store. If omitted and a persistence db_path is
            configured, a SqliteHITLStore is created automatically.

    Raises:
        RuntimeError: If the HITL store is not configured when needed.
    """
    agent_cfg = config or AgentConfig()
    gateway = auth_gateway or AuthorizationGateway(policy=AutoApprovePolicy())

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
        except RuntimeError as exc:
            # HITL pause — persist to durable store
            session_id = request.session_id or "unknown"
            if _hitl is not None:
                now = datetime.now(timezone.utc).isoformat()
                import uuid

                hitl_session = HITLSession(
                    session_id=session_id,
                    user_id="default",
                    thread_id=session_id,
                    status=HITLSessionStatus.PENDING,
                    tool_name="unknown",
                    tool_args={},
                    authorization_decision="PENDING",
                    approval_requirement="required",
                    idempotency_key=str(uuid.uuid4()),
                    version=1,
                    created_at=now,
                    updated_at=now,
                    expires_at=None,
                )
                await _hitl.insert(hitl_session)

            raise HTTPException(
                status_code=202,
                detail=f"Action requires approval. Use POST /agent/approve with session_id={session_id}",
            ) from exc
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
        if _hitl is None:
            raise HTTPException(status_code=501, detail="HITL store not configured")

        session = await _hitl.get(request.session_id)
        if session is None:
            raise HTTPException(status_code=404, detail=f"No session: {request.session_id}")

        if session.is_terminal():
            raise HTTPException(status_code=409, detail=f"Session already {session.status.value}")

        if session.is_expired():
            await _hitl.update_status(
                session.session_id, HITLSessionStatus.EXPIRED, expected_version=session.version
            )
            raise HTTPException(status_code=410, detail="Session expired")

        if request.decision == "reject":
            ok = await _hitl.update_status(
                session.session_id, HITLSessionStatus.REJECTED, expected_version=session.version
            )
            if not ok:
                raise HTTPException(status_code=409, detail="Concurrent modification detected")
            return {
                "session_id": session.session_id,
                "decision": "rejected",
                "result": {"final_answer": "Operation was rejected by human operator."},
            }

        # Approve: mark as APPROVED then resume
        ok = await _hitl.update_status(
            session.session_id, HITLSessionStatus.APPROVED, expected_version=session.version
        )
        if not ok:
            raise HTTPException(status_code=409, detail="Concurrent modification detected")

        # Create a temporary auto-approve gateway for the resumed execution
        resume_gateway = AuthorizationGateway(policy=AutoApprovePolicy())
        resume_runtime = AgentRuntime(
            config=agent_cfg,
            llm=llm,
            mcp_client=mcp_client,
            auth_gateway=resume_gateway,
        )

        try:
            result = await resume_runtime.run(
                f"Resume session {session.session_id}",
                run_id=session.session_id,
                resume_from_state={
                    "messages": [],
                    "step_count": 0,
                    "executed_tool_ids": set(),
                },
            )
            await _hitl.update_status(
                session.session_id,
                HITLSessionStatus.RESUMED,
                expected_version=session.version + 1,
            )
            return {
                "session_id": session.session_id,
                "decision": "approved",
                "result": {
                    "answer": result.get("final_answer"),
                    "step_count": result.get("step_count", 0),
                },
            }
        except Exception as exc:
            await _hitl.update_status(
                session.session_id,
                HITLSessionStatus.FAILED,
                expected_version=session.version + 1,
            )
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    return app
