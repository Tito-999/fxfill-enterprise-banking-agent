"""Typed state for the LangGraph banking agent.

The state flows through the graph: agent reasoning → tool execution →
(routing) → back to reasoning or finish.
"""

from __future__ import annotations

from typing import Annotated

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class AgentState(TypedDict):
    """Typed state carried through the banking agent graph.

    Attributes:
        messages: Conversation history. The ``add_messages`` reducer
            appends new messages rather than overwriting.
        final_answer: Set when the agent decides it is done.
        step_count: Monotonic counter incremented after each agent
            reasoning step. Enforces the ``max_agent_steps`` limit.
        session_id: Opaque session identifier for trace correlation
            and checkpoint grouping (Phase 2).
    """

    messages: Annotated[list[BaseMessage], add_messages]
    final_answer: str | None
    step_count: int
    session_id: str | None
