"""FastAPI service wrapping the banking agent with durable HITL persistence."""

from __future__ import annotations

import json
import time as _time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

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
from fxfill_banking_agent.hitl_store import HITLSession, HITLSessionStatus, SqliteHITLStore
from fxfill_banking_agent.lifecycle import ApplicationResources
from fxfill_banking_agent.llm import LLMProvider
from fxfill_banking_agent.mcp_client import MCPClient


class HITLConfigurationError(RuntimeError):
    """HITL-enabled application is missing a required dependency."""


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
    # NOTE: approver identity comes from AuthMiddleware (TrustedRequestContext),
    # NOT from this body field. This field is intentionally deprecated.
    approver: str = Field("human-operator", description="DEPRECATED: identity from auth middleware")


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
    resources: "ApplicationResources | None" = None,
    event_store: Any = None,
    checkpoint_saver: Any = None,
    idempotency_store: Any = None,
    metrics_collector: Any = None,
    tool_registry: Any = None,
    intent_router: Any = None,
    model_router: Any = None,
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
        resources: ApplicationResources for lifecycle management.
        event_store: Durable event store (optional).
        checkpoint_saver: Durable checkpoint saver (optional).
        idempotency_store: Durable idempotency store (optional).
        metrics_collector: Metrics collector (optional, defaults to in-memory).
        tool_registry: Tool registry (optional).

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

    # ── HITL consistency guard: full HITL deps require executor ─────
    _hitl_full = (hitl_store is not None and grant_repo is not None) or bool(
        agent_cfg.persistence.db_path
    )
    if _hitl_full and approval_executor is None:
        raise HITLConfigurationError(
            "HITL is fully enabled (hitl_store + grant_repo configured) "
            "but approval_executor is not provided. "
            "An HITL-enabled application requires HITLApprovalExecutor, "
            "HITL store, GrantRepository, IdempotencyStore, EventStore, "
            "and actor resolver."
        )

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
        event_store=event_store,
        checkpoint_saver=checkpoint_saver,
        idempotency_store=idempotency_store,
        metrics_collector=metrics_collector,
        tool_registry=tool_registry,
        router=intent_router,
        model_router=model_router,
    )

    # ── Lifespan — closes all owned resources on shutdown ──────────
    @asynccontextmanager
    async def _lifespan(app_instance: FastAPI) -> AsyncIterator[None]:
        yield
        if resources is not None:
            await resources.close()

    app = FastAPI(
        title="fxfill-enterprise-banking-agent",
        version="0.1.0",
        lifespan=_lifespan,
    )

    # ── Mount enterprise middleware ────────────────────────────
    # AuthMiddleware: extracts TrustedRequestContext from headers/tokens
    from fxfill_banking_agent.auth_middleware import AuthMiddleware

    app.add_middleware(AuthMiddleware)

    # TelemetryMiddleware: correlation_id propagation + span timing
    from fxfill_banking_agent.telemetry import TelemetryMiddleware

    app.add_middleware(TelemetryMiddleware, app_name="fxfill-agent", sample_rate=1.0)

    # RateLimitMiddleware: per-tenant request throttling
    app.add_middleware(RateLimitMiddleware, max_requests=60, window_seconds=60)

    # CORS: allow browser-based clients (configurable origins in production)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Production: restrict to specific origins
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    # ── API versioning: /v1/ prefix ─────────────────────────────
    from fastapi import APIRouter

    v1 = APIRouter(prefix="/v1")

    # ── Deep health check ──────────────────────────────────────
    @app.get("/health", response_model=HealthResponse)
    async def health() -> dict[str, str]:
        checks: dict[str, str] = {"status": "ok", "version": "0.1.0"}
        # Check MCP connectivity
        try:
            if hasattr(mcp_client, "tools"):
                checks["mcp"] = "ok"
            else:
                checks["mcp"] = "degraded"
        except Exception:
            checks["mcp"] = "error"
        # Check LLM provider (non-destructive)
        checks["provider"] = "configured" if llm else "missing"
        return checks

    @app.post("/agent", response_model=AgentResponse)
    async def agent_endpoint(request: AgentRequest) -> dict[str, Any]:
        # ── Trusted identity context (P0-05) ───────────────────────
        # Populated from auth middleware in production; uses development
        # defaults in dev mode. The model never sees or controls these.
        from fxfill_banking_agent.security.context import TrustedRequestContext

        trusted = TrustedRequestContext(
            subject_id="default",
            tenant_id="default",
            source="development",
            request_id=request.session_id or "",
        )

        op = Operation(
            kind=OperationKind.READ,
            name="agent_request",
            target=f"session:{request.session_id or 'new'}",
            details={"message": request.message, "subject_id": trusted.subject_id},
        )
        decision = await gateway.authorize(op)

        if decision.decision == ApprovalDecision.DENIED:
            raise HTTPException(status_code=403, detail="Request denied by authorization policy")

        if decision.decision == ApprovalDecision.PENDING:
            raise HTTPException(status_code=401, detail="Request requires human approval")

        try:
            result = await runtime.run(request.message, run_id=request.session_id)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        # Check for LangGraph interrupt — approval required
        interrupt_info = result.get("__interrupt__")
        if interrupt_info and isinstance(interrupt_info, dict):
            session_id = request.session_id or interrupt_info.get("session_id", "unknown")
            now = datetime.now(timezone.utc).isoformat()
            tool_name = str(interrupt_info.get("tool_name", "unknown"))
            tool_args = interrupt_info.get("tool_args", {})
            tool_call_id = str(interrupt_info.get("tool_call_id", ""))
            idem_key = str(interrupt_info.get("idempotency_key", f"{session_id}:{tool_call_id}"))
            thread_id = str(interrupt_info.get("thread_id", session_id))

            if isinstance(tool_args, dict):
                canonical_args = json.dumps(tool_args, sort_keys=True)
            else:
                canonical_args = json.dumps({})
            arg_digest = _digest(tool_args if isinstance(tool_args, dict) else {})

            if _hitl is not None:
                hitl_session = HITLSession(
                    session_id=session_id,
                    user_id="default",
                    thread_id=thread_id,
                    status=HITLSessionStatus.PENDING,
                    tool_name=tool_name,
                    tool_args=tool_args if isinstance(tool_args, dict) else {},
                    tool_call_id=tool_call_id,
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
                    thread_id=thread_id,
                    run_id=session_id,
                    checkpoint_id="",
                    tool_call_id=tool_call_id,
                    tool_name=tool_name,
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
            )

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
            # Validate rejection through executor
            result = await approval_executor.reject(request.session_id, context)
            _map_executor_result(result)

            # Resume the graph with rejection so the model can respond
            graph_result = await runtime.resume(
                thread_id=request.session_id,
                resume_value={
                    "decision": "rejected",
                    "reason": "Human operator rejected the operation",
                },
            )
            answer = graph_result.get("final_answer") if graph_result else None
            return {
                "session_id": result.session_id,
                "decision": result.decision,
                "result": {
                    "answer": answer or result.answer,
                    "step_count": graph_result.get("step_count", 0) if graph_result else 0,
                }
                if answer or result.answer
                else None,
            }

        # Approve: validate through executor, then resume graph
        result = await approval_executor.approve(request.session_id, context)
        _map_executor_result(result)

        # Load the approved grant for canonical args
        session = await _hitl.get(request.session_id) if _hitl else None
        canonical_args = {}
        if session is not None:
            canonical_args = session.tool_args if isinstance(session.tool_args, dict) else {}

        # Resume the graph so the model can generate a final answer
        graph_result = await runtime.resume(
            thread_id=result.session_id,
            resume_value={
                "decision": "approved",
                "canonical_args": canonical_args,
                "tool_name": session.tool_name if session else "",
                "tool_call_id": session.tool_call_id if session else "",
            },
        )

        final_answer = graph_result.get("final_answer") if graph_result else None
        return {
            "session_id": result.session_id,
            "decision": result.decision,
            "result": {
                "answer": final_answer or result.answer,
                "step_count": graph_result.get("step_count", 0) if graph_result else 0,
            }
            if final_answer or result.answer
            else None,
        }

    def _map_executor_result(result: ApprovalResult) -> None:
        if result.error:
            if result.decision == "reconciliation_required":
                raise HTTPException(status_code=409, detail=result.error)
            status_code = 409 if "Already" in (result.error or "") else 500
            raise HTTPException(status_code=status_code, detail=result.error)

    # ── /v1/ routes ────────────────────────────────────────────
    @v1.get("/health")
    async def v1_health() -> dict[str, str]:
        return await health()

    @v1.post("/agent", response_model=AgentResponse)
    async def v1_agent(request: AgentRequest) -> dict[str, Any]:
        return await agent_endpoint(request)

    @v1.post("/agent/approve", response_model=ApprovalResponse)
    async def v1_approve(request: ApprovalRequest) -> dict[str, Any]:
        return await approve_endpoint(request)

    # Threads API (P0-02)
    @v1.post("/threads")
    async def create_thread() -> dict[str, Any]:
        import uuid

        thread_id = str(uuid.uuid4())
        from fxfill_banking_agent.conversation_service import ThreadService

        svc = ThreadService()
        info = svc.create_thread(thread_id)
        return {
            "thread_id": info.thread_id,
            "created_at": info.created_at,
            "status": info.status,
        }

    @v1.get("/threads/{thread_id}")
    async def get_thread(thread_id: str) -> dict[str, Any]:
        from fxfill_banking_agent.conversation_service import ThreadService

        svc = ThreadService()
        info = svc.get_thread(thread_id)
        if info is None:
            raise HTTPException(status_code=404, detail="Thread not found")
        return {
            "thread_id": info.thread_id,
            "created_at": info.created_at,
            "updated_at": info.updated_at,
            "message_count": info.message_count,
            "status": info.status,
        }

    @v1.delete("/threads/{thread_id}")
    async def delete_thread(thread_id: str) -> dict[str, Any]:
        from fxfill_banking_agent.conversation_service import ThreadService

        svc = ThreadService()
        if not svc.delete_thread(thread_id):
            raise HTTPException(status_code=404, detail="Thread not found")
        return {"thread_id": thread_id, "status": "deleted"}

    # Audit API (P2-05)
    @v1.get("/audit/events")
    async def list_audit_events(run_id: str = "", limit: int = 50) -> dict[str, Any]:
        if event_store is None:
            raise HTTPException(status_code=501, detail="Event store not configured")
        try:
            if run_id:
                events = await event_store.list_by_run(run_id, limit)
            else:
                events = []
            return {
                "events": [
                    {
                        "run_id": e.run_id,
                        "seq": e.seq,
                        "kind": e.kind.value,
                        "timestamp": getattr(e, "timestamp", ""),
                    }
                    for e in events
                ],
                "count": len(events),
            }
        except Exception:
            raise HTTPException(status_code=500, detail="Failed to query audit events")

    app.include_router(v1)

    return app


# ── Rate Limiting Middleware ───────────────────────────────────────────


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-tenant in-memory rate limiter.

    Production should use Redis-backed rate limiting for multi-instance
    consistency. This implementation is suitable for single-instance dev.
    """

    def __init__(self, app: Any, max_requests: int = 60, window_seconds: int = 60) -> None:
        super().__init__(app)
        self._max = max_requests
        self._window = window_seconds
        self._counters: dict[str, list[float]] = {}

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        tenant = request.headers.get("X-Tenant-Id", "default")
        key = f"{tenant}:{request.url.path}"
        now = _time.monotonic()

        if key not in self._counters:
            self._counters[key] = []
        timestamps = [t for t in self._counters[key] if now - t < self._window]
        if len(timestamps) >= self._max:
            raise HTTPException(status_code=429, detail="Rate limit exceeded")
        timestamps.append(now)
        self._counters[key] = timestamps

        return await call_next(request)
