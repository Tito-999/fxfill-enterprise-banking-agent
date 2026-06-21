"""FastAPI service wrapping the banking agent.

Exposes the agent as an HTTP endpoint with request/response schemas,
a health-check endpoint, and HITL approve/reject endpoints.
"""

from __future__ import annotations

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
from fxfill_banking_agent.llm import LLMProvider
from fxfill_banking_agent.mcp_client import MCPClient

# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class AgentRequest(BaseModel):
    """Incoming request to the banking agent."""

    message: str = Field(
        ..., min_length=1, max_length=10000, description="User message to the agent"
    )
    session_id: str | None = Field(
        None, description="Session identifier for multi-turn conversations"
    )


class AgentResponse(BaseModel):
    """Response from the banking agent."""

    session_id: str
    answer: str | None
    step_count: int
    status: str = "complete"


class ApprovalRequest(BaseModel):
    """Request to approve or reject a pending operation."""

    session_id: str = Field(..., min_length=1, description="Session that requires approval")
    decision: str = Field(..., pattern="^(approve|reject)$", description="Approve or reject")
    approver: str = Field("human-operator", description="Identifier of the approver")


class ApprovalResponse(BaseModel):
    """Response after an approval decision."""

    session_id: str
    decision: str
    result: dict[str, Any] | None = None


class HealthResponse(BaseModel):
    """Health-check response."""

    status: str = "ok"
    version: str


# ---------------------------------------------------------------------------
# In-memory session store for HITL state
# ---------------------------------------------------------------------------

_paused_sessions: dict[str, dict[str, Any]] = {}

# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------


def create_app(
    llm: LLMProvider,
    mcp_client: MCPClient,
    config: AgentConfig | None = None,
    auth_gateway: AuthorizationGateway | None = None,
) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        llm: The LLM provider (real or mock).
        mcp_client: The MCP client (stub or real).
        config: Agent configuration override.
        auth_gateway: Authorization gateway (defaults to auto-approve).

    Returns:
        A configured FastAPI application ready to serve.
    """
    app = FastAPI(
        title="fxfill-enterprise-banking-agent",
        version="0.1.0",
        description="Production-oriented banking knowledge agent API",
    )

    gateway = auth_gateway or AuthorizationGateway(policy=AutoApprovePolicy())

    runtime = AgentRuntime(
        config=config or AgentConfig(),
        llm=llm,
        mcp_client=mcp_client,
        auth_gateway=gateway,
    )

    @app.get("/health", response_model=HealthResponse)
    async def health() -> dict[str, str]:
        """Health-check endpoint."""
        return {"status": "ok", "version": "0.1.0"}

    @app.post("/agent", response_model=AgentResponse)
    async def agent_endpoint(request: AgentRequest) -> dict[str, Any]:
        """Send a message to the banking agent."""
        # Authorize top-level request
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
            raise HTTPException(
                status_code=401,
                detail="Request requires human approval — use /agent/approve to proceed",
            )

        try:
            result = await runtime.run(
                request.message,
                run_id=request.session_id,
            )
        except RuntimeError as exc:
            # HITL pause — store state and return 202
            session_id = request.session_id or "unknown"
            _paused_sessions[session_id] = {
                "message": request.message,
                "error": str(exc),
            }
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
        """Approve or reject a paused agent session.

        When ``decision`` is ``"approve"``, the paused tool call is
        authorized and execution resumes. When ``"reject"``, the tool
        call is denied and the session ends.
        """
        session_id = request.session_id
        paused = _paused_sessions.pop(session_id, None)
        if paused is None:
            raise HTTPException(status_code=404, detail=f"No paused session: {session_id}")

        if request.decision == "reject":
            return {
                "session_id": session_id,
                "decision": "rejected",
                "result": {"final_answer": "Operation was rejected by human operator."},
            }

        # Approve: resume execution with a temporary auto-approve gateway
        resume_gateway = AuthorizationGateway(policy=AutoApprovePolicy())
        resume_runtime = AgentRuntime(
            config=config or AgentConfig(),
            llm=llm,
            mcp_client=mcp_client,
            auth_gateway=resume_gateway,
        )

        try:
            result = await resume_runtime.run(
                paused["message"],
                run_id=session_id,
                resume_from_state={
                    "messages": [],
                    "step_count": 0,
                    "executed_tool_ids": set(),
                },
            )
            return {
                "session_id": session_id,
                "decision": "approved",
                "result": {
                    "answer": result.get("final_answer"),
                    "step_count": result.get("step_count", 0),
                },
            }
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    return app
