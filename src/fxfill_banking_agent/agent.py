"""Wired agent runtime — composes graph, persistence, metrics, and logging."""

from __future__ import annotations

import time
import uuid
from typing import Any

from langchain_core.messages import HumanMessage
from langgraph.types import Command

from fxfill_banking_agent.auth import AuthorizationGateway
from fxfill_banking_agent.checkpoint_store import SqliteCheckpointSaver
from fxfill_banking_agent.config import AgentConfig
from fxfill_banking_agent.graph import build_agent_graph
from fxfill_banking_agent.idempotency_store import IdempotencyStore
from fxfill_banking_agent.llm import LLMProvider
from fxfill_banking_agent.logging import get_logger
from fxfill_banking_agent.mcp_client import MCPClient
from fxfill_banking_agent.metrics import InMemoryMetricsCollector, MetricsCollector
from fxfill_banking_agent.model_router import ModelRouter
from fxfill_banking_agent.persistence import AgentEvent, EventKind, EventStore
from fxfill_banking_agent.routing.policies import RouteKind
from fxfill_banking_agent.routing.router import Router
from fxfill_banking_agent.state import AgentState
from fxfill_banking_agent.tools.registry import ToolRegistry

logger = get_logger(__name__)


def _extract_json_block(text: str) -> str:
    """Extract JSON from LLM response, handling markdown fences."""
    import re

    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if match:
        return match.group(1).strip()
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        return match.group(0).strip()
    return text.strip()


class AgentRuntime:
    """Composed agent runtime with graph, persistence, metrics, and logging."""

    # ── Tools that MUST have server-injected user_id ───────────────
    _IDENTITY_TOOLS: frozenset[str] = frozenset(
        {
            "get_account_summary",
            "get_balance",
            "list_transactions",
            "create_transfer_draft",
            "submit_transfer",
            "cancel_transfer",
            "report_suspicious_transaction",
        }
    )

    def __init__(
        self,
        *,
        config: AgentConfig | None = None,
        llm: LLMProvider,
        mcp_client: MCPClient,
        event_store: EventStore | None = None,
        metrics_collector: MetricsCollector | None = None,
        auth_gateway: AuthorizationGateway | None = None,
        checkpoint_saver: Any | None = None,
        idempotency_store: IdempotencyStore | None = None,
        tool_registry: ToolRegistry | None = None,
        router: Router | None = None,
        model_router: ModelRouter | None = None,
    ) -> None:
        self.config = config or AgentConfig()
        self.llm = llm
        self.mcp_client = mcp_client
        self.event_store = event_store
        self.metrics_collector = metrics_collector or InMemoryMetricsCollector()
        if auth_gateway is None:
            raise RuntimeError(
                "AgentRuntime requires an explicit AuthorizationGateway — refusing to fail open"
            )
        self.auth_gateway = auth_gateway
        self.router = router
        self.model_router = model_router

        # Use durable SQLite checkpoint by default if a db path is configured
        if checkpoint_saver is not None:
            self.checkpoint_saver = checkpoint_saver
        elif self.config.persistence.db_path:
            self.checkpoint_saver = SqliteCheckpointSaver(self.config.persistence.db_path)
        else:
            from langgraph.checkpoint.memory import MemorySaver

            self.checkpoint_saver = MemorySaver()

        self.idempotency_store = idempotency_store
        self.tool_registry = tool_registry

        self._graph = build_agent_graph(checkpointer=self.checkpoint_saver)

    async def _persist_event(
        self, run_id: str, seq: int, kind: EventKind, payload: dict[str, object]
    ) -> None:
        if self.event_store is None:
            return
        try:
            await self.event_store.insert(
                AgentEvent(run_id=run_id, seq=seq, kind=kind, payload=payload)
            )
        except Exception:
            logger.warning("event_persist_failed", run_id=run_id, seq=seq, kind=kind.value)

    async def run(
        self,
        user_message: str,
        *,
        run_id: str | None = None,
        thread_id: str | None = None,
        resume_from_state: dict[str, Any] | None = None,
        trusted_context: Any = None,
    ) -> dict[str, Any]:
        run_id = run_id or str(uuid.uuid4())
        thread_id = thread_id or run_id
        logger.info("agent_run_start", run_id=run_id, thread_id=thread_id)

        self.metrics_collector.start_run(run_id)

        if resume_from_state:
            state: AgentState = {
                "messages": resume_from_state.get("messages", []),
                "session_id": run_id,
                "step_count": resume_from_state.get("step_count", 0),
                "final_answer": resume_from_state.get("final_answer"),
                "executed_tool_ids": resume_from_state.get("executed_tool_ids", set()),
                "pending_approvals": resume_from_state.get("pending_approvals", []),
            }
            seq = state.get("step_count", 0)
        else:
            state = {
                "messages": [HumanMessage(content=user_message)],
                "session_id": run_id,
                "step_count": 0,
                "final_answer": None,
                "executed_tool_ids": set(),
                "pending_approvals": [],
            }
            seq = 0
            await self._persist_event(
                run_id, seq, EventKind.USER_MESSAGE, {"content": user_message}
            )

        # ── Intent classification (P1-01) ─────────────────────────
        route = None
        if self.router is not None:
            route = self.router.route(user_message)
            logger.info(
                "intent_classified",
                intent=route.intent.value,
                route=route.kind.value,
                reason=route.reason,
            )
            await self._persist_event(
                run_id,
                seq + 1,
                EventKind.CHECKPOINT,
                {
                    "kind": "INTENT_CLASSIFIED",
                    "intent": route.intent.value,
                    "route": route.kind.value,
                },
            )

            # ModelRouter: select LLM tier based on intent
            if self.model_router is not None:
                model_route = self.model_router.route_for_intent(
                    route.intent.value, risk_level="low"
                )
                logger.info(
                    "model_routing",
                    intent=route.intent.value,
                    tier=model_route.tier.value,
                    model=model_route.model,
                )

            # DIRECT route: LLM extracts args → tool called directly
            if route.kind == RouteKind.DIRECT and route.suggested_tools and not resume_from_state:
                result = await self._execute_direct(
                    route, run_id, thread_id, user_message, trusted_context=trusted_context
                )
                if result is not None:
                    self.metrics_collector.finish_run()
                    return result

            # PLANNER route: full Planner→Executor→Verifier loop
            if route.kind == RouteKind.PLANNER and not resume_from_state:
                result = await self._execute_planner(route, run_id, thread_id, user_message)
                if result is not None:
                    self.metrics_collector.finish_run()
                    return result

            # RAG route: retrieve knowledge then respond
            if route.kind == RouteKind.RAG and not resume_from_state:
                result = await self._execute_rag(route, run_id, user_message)
                if result is not None:
                    self.metrics_collector.finish_run()
                    return result

            # REJECT route: unsupported or out-of-scope
            if route.kind == RouteKind.REJECT:
                self.metrics_collector.finish_run()
                return {
                    "session_id": run_id,
                    "final_answer": (
                        "I'm sorry, but I can't help with that request. "
                        "I can assist with account inquiries, transfers, "
                        "beneficiary lookups, and policy questions."
                    ),
                    "step_count": 0,
                    "status": "rejected",
                }

            # TRANSFER_STATE_MACHINE route: structured transfer workflow
            if route.kind == RouteKind.TRANSFER_STATE_MACHINE and not resume_from_state:
                result = await self._execute_transfer_workflow(
                    route, run_id, thread_id, user_message
                )
                if result is not None:
                    self.metrics_collector.finish_run()
                    return result

        t0 = time.monotonic()
        graph_config = {
            "configurable": {
                "llm": self.llm,
                "mcp_client": self.mcp_client,
                "agent_config": self.config,
                "auth_gateway": self.auth_gateway,
                "idempotency_store": self.idempotency_store,
                "tool_registry": self.tool_registry,
                "metrics_collector": self.metrics_collector,
                "thread_id": thread_id,
                "run_id": run_id,
            },
        }

        try:
            result = await self._graph.ainvoke(state, config=graph_config)
        except RuntimeError as exc:
            logger.error("agent_run_error", run_id=run_id, error=str(exc))
            await self._persist_event(
                run_id,
                state.get("step_count", 0) + 1,
                EventKind.CHECKPOINT,
                {"state": {"step_count": state.get("step_count", 0), "session_id": run_id}},
            )
            raise

        # Detect LangGraph interrupt — the graph suspended waiting for HITL approval
        if "__interrupt__" in result:
            interrupts = result["__interrupt__"]
            interrupt_info = interrupts[0].value if interrupts else {}
            await self._persist_event(
                run_id,
                state.get("step_count", 0) + 1,
                EventKind.CHECKPOINT,
                {"kind": "HITL_INTERRUPT", "interrupt": interrupt_info},
            )
            # Return the interrupt info so the caller can create HITL sessions
            return {
                "__interrupt__": interrupt_info,
                "session_id": run_id,
                "step_count": state.get("step_count", 0),
            }

        elapsed_ms = (time.monotonic() - t0) * 1000

        await self._persist_event(
            run_id,
            state.get("step_count", 0) + 1,
            EventKind.AGENT_MESSAGE,
            {"final_answer": result.get("final_answer")},
        )

        run_metrics = self.metrics_collector.finish_run()
        logger.info(
            "agent_run_complete",
            run_id=run_id,
            steps=len(run_metrics.steps),
            duration_ms=round(elapsed_ms, 1),
            total_tokens=run_metrics.total_input_tokens + run_metrics.total_output_tokens,
        )

        return result  # type: ignore[no-any-return]

    async def _execute_direct(
        self,
        route: Any,
        run_id: str,
        thread_id: str,
        user_message: str = "",
        trusted_context: Any = None,
    ) -> dict[str, Any] | None:
        """Execute a DIRECT route: LLM extracts args, tool is called, result returned.

        This avoids the full ReAct loop for simple queries like "What's my balance?"
        """
        if not route.suggested_tools:
            return None

        tool_name = route.suggested_tools[0]
        logger.info("direct_route", tool=tool_name, run_id=run_id)

        # Fail closed: identity-sensitive tools require authenticated user
        if tool_name in self._IDENTITY_TOOLS:
            if trusted_context is None:
                return {
                    "session_id": run_id,
                    "final_answer": "Authentication is required for this operation.",
                    "step_count": 1,
                    "status": "auth_required",
                }
            subject = getattr(trusted_context, "subject_id", "")
            if subject in ("anonymous", ""):
                return {
                    "session_id": run_id,
                    "final_answer": "Authentication is required for this operation.",
                    "step_count": 1,
                    "status": "auth_required",
                }

        from langchain_core.messages import SystemMessage

        # Use LLM to extract structured arguments for the tool.
        # NEVER ask LLM for user_id — it will be server-injected.
        system = SystemMessage(
            content=(
                f"You are a banking assistant. Extract the required parameters "
                f"for the tool '{tool_name}' from the user's request. "
                f"Do NOT include user_id or tenant_id — these are handled by the system. "
                f"Respond with ONLY a JSON object. Do not add any other text."
            )
        )
        user = HumanMessage(content=user_message)

        try:
            response = await self.llm.invoke([system, user], tools=None, tool_choice="none")
            raw = str(getattr(response, "content", "")).strip()

            import json as _json

            # Extract JSON from response
            args = _json.loads(_extract_json_block(raw))
        except Exception:
            logger.warning("direct_arg_extraction_failed", tool=tool_name)
            return {
                "session_id": run_id,
                "final_answer": (
                    "I had trouble understanding your request. Could you rephrase it "
                    "with the specific account or details you're asking about?"
                ),
                "step_count": 1,
                "status": "error_recovery",
            }

        # ── Server-inject identity fields, override any LLM value ──────
        if tool_name in self._IDENTITY_TOOLS and trusted_context is not None:
            subject = getattr(trusted_context, "subject_id", "")
            tenant = getattr(trusted_context, "tenant_id", "default")
            args["user_id"] = subject
            args["tenant_id"] = tenant

        # Execute the tool directly
        from fxfill_banking_agent.mcp_client import ToolCall

        call = ToolCall(name=tool_name, arguments=args)
        result = await self.mcp_client.call_tool(call)

        final_answer = result.content if result.success else f"Error: {result.error}"
        await self._persist_event(
            run_id, 2, EventKind.AGENT_MESSAGE, {"final_answer": final_answer}
        )

        return {
            "session_id": run_id,
            "final_answer": final_answer,
            "step_count": 1,
            "messages": [user, response],
        }

    async def _execute_planner(
        self,
        route: Any,
        run_id: str,
        thread_id: str,
        user_message: str = "",
    ) -> dict[str, Any] | None:
        """Execute a PLANNER route: full P→E→V loop for complex tasks.

        1. Planner generates an ExecutionPlan
        2. Validator checks it
        3. Executor runs each step → Verifier checks result
        4. On completion, returns structured result
        """
        from fxfill_banking_agent.orchestration.executor import StepExecutor
        from fxfill_banking_agent.orchestration.models import PlanStatus
        from fxfill_banking_agent.orchestration.planner import Planner
        from fxfill_banking_agent.orchestration.validator import PlanValidator
        from fxfill_banking_agent.orchestration.verifier import StepVerifier

        logger.info("planner_route", run_id=run_id)

        planner = Planner(self.llm, self.tool_registry)
        validator = PlanValidator(self.tool_registry, max_steps=route.max_steps or 15)
        executor = StepExecutor(self.mcp_client, self.auth_gateway, self.tool_registry)
        verifier = StepVerifier()

        # Phase 1: Plan
        plan = await planner.plan(user_message)
        if plan.status == PlanStatus.REJECTED:
            return {
                "session_id": run_id,
                "final_answer": "I could not create a valid plan for this request. Could you rephrase?",
                "step_count": 0,
            }

        validation = validator.validate(plan)
        if not validation.valid:
            logger.warning("plan_invalid", errors=validation.errors)
            return {
                "session_id": run_id,
                "final_answer": f"I'm unable to process this request: {validation.reason}",
                "step_count": 0,
            }

        await self._persist_event(
            run_id,
            1,
            EventKind.CHECKPOINT,
            {"kind": "PLAN_CREATED", "plan_id": plan.plan_id, "steps": plan.step_count},
        )

        # Phase 2: Execute steps
        results: list[Any] = []
        for step in plan.steps:
            step_result = await executor.execute_step(plan, step)
            verdict = verifier.verify(step, step_result, plan)

            if not verdict.passed:
                if verdict.action == "retry" and step.max_retries > 0:
                    step_result = await executor.execute_step(plan, step)
                    verdict = verifier.verify(step, step_result, plan)
                elif verdict.action in ("abort", "ask_user"):
                    return {
                        "session_id": run_id,
                        "final_answer": f"Step '{step.objective}' failed: {verdict.reason}",
                        "step_count": len(results) + 1,
                    }

            results.append(step_result)

        # Phase 3: Synthesize final answer
        summary = "\n".join(f"- {r.output[:200]}" for r in results if r.success)
        return {
            "session_id": run_id,
            "final_answer": f"Task completed in {len(results)} steps:\n{summary}",
            "step_count": len(results),
        }

    async def _execute_rag(
        self,
        route: Any,
        run_id: str,
        user_message: str = "",
    ) -> dict[str, Any] | None:
        """Execute a RAG route: retrieve knowledge, then respond with citations.

        Uses InMemoryRetriever if pre-loaded with documents. Falls back
        to the graph for un-indexed knowledge domains.
        """
        logger.info("rag_route", run_id=run_id)

        # Try to use in-memory retriever if available
        try:
            from fxfill_banking_agent.rag.retriever import InMemoryRetriever

            retriever = getattr(self, "_rag_retriever", None)
            if retriever is not None and isinstance(retriever, InMemoryRetriever):
                result = retriever.retrieve(user_message, top_k=3)
                if result.chunks:
                    citations = result.citations
                    context = "\n\n".join(
                        f"{c.to_text()}\n{chunk.content[:500]}"
                        for c, chunk in zip(citations, result.chunks)
                    )

                    from langchain_core.messages import SystemMessage

                    system = SystemMessage(
                        content=(
                            "You are a banking knowledge assistant. Answer the user's "
                            "question based ONLY on the provided document excerpts. "
                            "Cite your sources. If the documents don't contain the "
                            "answer, say 'The knowledge base does not contain this "
                            "information.'\n\n"
                            f"Documents:\n{context}"
                        )
                    )
                    user = HumanMessage(content=user_message)
                    response = await self.llm.invoke([system, user], tools=None, tool_choice="none")
                    answer = str(getattr(response, "content", ""))
                    await self._persist_event(
                        run_id, 2, EventKind.AGENT_MESSAGE, {"final_answer": answer}
                    )
                    return {
                        "session_id": run_id,
                        "final_answer": answer,
                        "step_count": 1,
                    }
        except Exception:
            pass

        # No RAG backend configured — generate a helpful fallback
        from langchain_core.messages import SystemMessage

        system = SystemMessage(
            content=(
                "You are a banking knowledge assistant. Answer the user's question "
                "to the best of your knowledge, but clearly state when you are "
                "uncertain. Never fabricate specific fee amounts, policy details, "
                "or regulatory information. Suggest the user contact their bank "
                "for definitive answers."
            )
        )
        user = HumanMessage(content=user_message)
        response = await self.llm.invoke([system, user], tools=None, tool_choice="none")
        answer = str(getattr(response, "content", ""))
        await self._persist_event(run_id, 2, EventKind.AGENT_MESSAGE, {"final_answer": answer})
        return {
            "session_id": run_id,
            "final_answer": answer,
            "step_count": 1,
        }

    async def _execute_transfer_workflow(
        self,
        route: Any,
        run_id: str,
        thread_id: str,
        user_message: str = "",
    ) -> dict[str, Any] | None:
        """Execute a TRANSFER_STATE_MACHINE route.

        Transfers follow a structured workflow:
        1. Confirm account and beneficiary
        2. Create transfer draft
        3. Show summary and request approval
        4. Submit on approval
        """
        logger.info("transfer_workflow", run_id=run_id)

        # Transfer state machine: structured workflow with confirmation
        from langchain_core.messages import SystemMessage

        system = SystemMessage(
            content=(
                "You are a banking transfer assistant. Help the user create a transfer "
                "by extracting: source_account_id, beneficiary name/id, amount, and currency. "
                "After creating a draft, summarize the transfer details and ask for "
                "confirmation before submitting. Use the tools: find_beneficiary, "
                "create_transfer_draft. Do NOT call submit_transfer — the user must "
                "explicitly confirm first."
            )
        )
        user = HumanMessage(content=user_message)
        try:
            response = await self.llm.invoke(
                [system, user],
                tools=self.tool_registry.provider_definitions(include_server_fields=False)
                if self.tool_registry
                else None,
                tool_choice="auto",
            )
        except Exception:
            return {
                "session_id": run_id,
                "final_answer": (
                    "I was unable to process your transfer request. Please try again "
                    "with the recipient name, amount, and currency clearly specified."
                ),
                "step_count": 0,
                "status": "error",
            }

        # Let the graph handle tool execution (with HITL for submit_transfer)
        tf_config = {
            "configurable": {
                "llm": self.llm,
                "mcp_client": self.mcp_client,
                "agent_config": self.config,
                "auth_gateway": self.auth_gateway,
                "idempotency_store": self.idempotency_store,
                "tool_registry": self.tool_registry,
                "metrics_collector": self.metrics_collector,
                "thread_id": thread_id,
                "run_id": run_id,
            },
        }
        result = await self._graph.ainvoke(
            {"messages": [user, response], "session_id": run_id, "step_count": 1},
            config=tf_config,
        )

        final = result.get("final_answer") or str(
            getattr(result.get("messages", [None])[-1], "content", "")
            if result.get("messages")
            else "Transfer processed."
        )
        return {
            "session_id": run_id,
            "final_answer": final,
            "step_count": result.get("step_count", 1),
        }

    async def resume(
        self,
        *,
        thread_id: str,
        resume_value: dict[str, Any],
        run_id: str | None = None,
    ) -> dict[str, Any]:
        """Resume a suspended graph after HITL approval.

        Calls the graph with ``Command(resume=...)`` so that LangGraph
        continues from the ``interrupt()`` call point.

        Args:
            thread_id: The thread that was suspended (must match the
                thread_id from the original run).
            resume_value: Value passed back to the ``interrupt()`` call.
                Expected keys: ``decision``, ``canonical_args``, ``reason``.
            run_id: Optional run identifier for tracing.

        Returns:
            The final graph state after resume and completion.
        """
        run_id = run_id or str(uuid.uuid4())
        logger.info("agent_run_resume", run_id=run_id, thread_id=thread_id)

        self.metrics_collector.start_run(run_id)

        graph_config = {
            "configurable": {
                "llm": self.llm,
                "mcp_client": self.mcp_client,
                "agent_config": self.config,
                "auth_gateway": self.auth_gateway,
                "idempotency_store": self.idempotency_store,
                "tool_registry": self.tool_registry,
                "metrics_collector": self.metrics_collector,
                "thread_id": thread_id,
                "run_id": run_id,
            },
        }

        try:
            result = await self._graph.ainvoke(Command(resume=resume_value), config=graph_config)
        except RuntimeError as exc:
            logger.error("agent_resume_error", run_id=run_id, error=str(exc))
            raise

        await self._persist_event(
            run_id,
            0,
            EventKind.AGENT_MESSAGE,
            {"final_answer": result.get("final_answer")},
        )

        self.metrics_collector.finish_run()
        return result  # type: ignore[no-any-return]
