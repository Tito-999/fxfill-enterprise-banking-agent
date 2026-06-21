"""Typed state for the LangGraph banking agent.

The state flows through the graph: agent reasoning → tool execution →
(routing) → back to reasoning or finish.
"""

from __future__ import annotations

from typing import Annotated

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class AgentState(TypedDict, total=False):
    """Typed state carried through the banking agent graph.

    All keys are ``total=False`` so that partial state updates work
    correctly with LangGraph's reducer semantics.

    Attributes:
        messages: Conversation history. The ``add_messages`` reducer
            appends new messages rather than overwriting.
        final_answer: Set when the agent decides it is done.
        step_count: Monotonic counter incremented after each agent
            reasoning step. Enforces the ``max_agent_steps`` limit.
        session_id: Opaque session identifier for trace correlation
            and checkpoint grouping.
        executed_tool_ids: Set of tool call IDs already executed
            (for idempotency after resume).
        pending_approvals: Tool calls awaiting human approval.
    """

    messages: Annotated[list[BaseMessage], add_messages]
    final_answer: str | None
    step_count: int
    session_id: str | None
    executed_tool_ids: set[str]
    pending_approvals: list[dict[str, object]]
