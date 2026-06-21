"""Typed HITL pause signal — replaces RuntimeError("HITL:...") string parsing.

This is a normal domain event, not an unexpected runtime failure.
"""

from __future__ import annotations


class HITLPending(Exception):
    """Typed signal emitted when a tool call requires human approval.

    The API catches this exception specifically, distinguishes it from
    real RuntimeErrors, and stores a durable HITL session before
    returning 202 to the caller.
    """

    def __init__(
        self,
        *,
        tool_name: str,
        tool_args: dict | None = None,
        tool_call_id: str = "",
        session_id: str = "",
        thread_id: str = "",
        idempotency_key: str = "",
    ) -> None:
        self.tool_name = tool_name
        self.tool_args = tool_args or {}
        self.tool_call_id = tool_call_id
        self.session_id = session_id
        self.thread_id = thread_id
        self.idempotency_key = idempotency_key
        super().__init__(
            f"HITLPending(tool={tool_name}, session={session_id}, "
            f"idem={idempotency_key[:16] if idempotency_key else 'none'})"
        )
