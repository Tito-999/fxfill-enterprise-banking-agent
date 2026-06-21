"""FastAPI service wrapping the banking agent.

Exposes the agent as an HTTP endpoint with request/response schemas
and a health-check endpoint.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from fxfill_banking_agent.agent import AgentRuntime
from fxfill_banking_agent.auth import AuthorizationGateway, AutoApprovePolicy
from fxfill_banking_agent.config import AgentConfig
from fxfill_banking_agent.llm import LLMProvider
from fxfill_banking_agent.mcp_client import MCPClient

# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class AgentRequest(BaseModel):
    """Incoming request to the banking agent.

    Attributes:
        message: The user's natural-language banking request.
        session_id: Optional session identifier for multi-turn
            conversations. Auto-generated if omitted.
    """

    message: str = Field(
        ..., min_length=1, max_length=10000, description="User message to the agent"
    )
    session_id: str | None = Field(
        None, description="Session identifier for multi-turn conversations"
    )


class AgentResponse(BaseModel):
    """Response from the banking agent.

    Attributes:
        session_id: The session identifier (echoed from request or auto-generated).
        answer: The agent's final answer.
        step_count: Number of reasoning steps taken.
    """

    session_id: str
    answer: str | None
    step_count: int


class HealthResponse(BaseModel):
    """Health-check response."""

    status: str = "ok"
    version: str


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------


def create_app(
    llm: LLMProvider,
    mcp_client: MCPClient,
    config: AgentConfig | None = None,
) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        llm: The LLM provider (real or mock).
        mcp_client: The MCP client (stub or real).
        config: Agent configuration override.

    Returns:
        A configured FastAPI application ready to serve.
    """
    app = FastAPI(
        title="fxfill-enterprise-banking-agent",
        version="0.1.0",
        description="Production-oriented banking knowledge agent API",
    )

    # We create a single runtime instance shared across requests.
    # In production this would be managed by a connection pool.
    runtime = AgentRuntime(
        config=config or AgentConfig(),
        llm=llm,
        mcp_client=mcp_client,
    )
    auth_gateway = AuthorizationGateway(policy=AutoApprovePolicy())

    @app.get("/health", response_model=HealthResponse)
    async def health() -> dict[str, str]:
        """Health-check endpoint."""
        return {"status": "ok", "version": "0.1.0"}

    @app.post("/agent", response_model=AgentResponse)
    async def agent_endpoint(request: AgentRequest) -> dict[str, Any]:
        """Send a message to the banking agent."""
        # Authorize the operation
        from fxfill_banking_agent.auth import Operation, OperationKind

        op = Operation(
            kind=OperationKind.READ,
            name="agent_request",
            target=f"session:{request.session_id or 'new'}",
            details={"message": request.message},
        )
        decision = await auth_gateway.authorize(op)

        if decision.decision.value == "denied":
            raise HTTPException(status_code=403, detail="Request denied by authorization policy")

        if decision.decision.value == "pending":
            raise HTTPException(
                status_code=401,
                detail="Request requires human approval — not available in this deployment",
            )

        try:
            result = await runtime.run(request.message, run_id=request.session_id)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        return {
            "session_id": result.get("session_id", ""),
            "answer": result.get("final_answer"),
            "step_count": result.get("step_count", 0),
        }

    return app
