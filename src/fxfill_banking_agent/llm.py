"""LLM abstraction for the banking agent.

Provides a protocol that can be backed by a real model provider or a
deterministic mock for testing.
"""

from __future__ import annotations

from typing import Any, Protocol

from langchain_core.messages import AIMessage, BaseMessage


class LLMProvider(Protocol):
    """Protocol for a language model that the agent graph calls.

    In development / testing this is a deterministic mock. In later
    phases it wraps a real provider via langchain-core's ChatModel.
    """

    async def invoke(
        self,
        messages: list[BaseMessage],
        *,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> AIMessage:
        """Invoke the model with a list of messages.

        Args:
            messages: The conversation history.
            tools: Optional tool schemas in provider-native format.
            tool_choice: Optional tool selection control
                (``"auto"``, ``"none"``, ``"required"``, or a specific tool dict).

        Returns:
            The model's response as an AIMessage.
        """
        ...


class MockLLM:
    """Deterministic mock LLM for testing the agent graph.

    Returns a fixed sequence of responses. When exhausted it raises
    ``StopIteration`` so that test assertions can verify the exact
    number of calls.
    """

    def __init__(self, responses: list[AIMessage] | None = None) -> None:
        """Create a mock LLM with a pre-defined response queue.

        Args:
            responses: Messages to return in order. If empty, defaults
                to a single "done" message.
        """
        self._responses: list[AIMessage] = responses or [
            AIMessage(content="No further actions needed.")
        ]
        self._index = 0
        self.call_count = 0

    async def invoke(
        self,
        messages: list[BaseMessage],
        *,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> AIMessage:
        """Return the next canned response.

        Args:
            messages: The conversation history (recorded but canned responses are fixed).
            tools: Optional tool schemas (ignored by mock — response is pre-scripted).
            tool_choice: Optional tool selection control (ignored by mock).

        Raises:
            StopIteration: When the response queue is exhausted.
        """
        if self._index >= len(self._responses):
            raise RuntimeError(f"MockLLM exhausted after {len(self._responses)} response(s)")
        response = self._responses[self._index]
        self._index += 1
        self.call_count += 1
        return response

    @property
    def exhausted(self) -> bool:
        """True when all canned responses have been consumed."""
        return self._index >= len(self._responses)


class EchoLLM:
    """Mock LLM that echoes the last user message back as its response.

    Useful for integration tests where you want deterministic but
    varied output without pre-scripting every response.
    """

    def __init__(self, prefix: str = "Echo: ") -> None:
        self._prefix = prefix
        self.call_count = 0

    async def invoke(
        self,
        messages: list[BaseMessage],
        *,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> AIMessage:
        """Return the last human message prefixed with ``Echo: ``.

        Args:
            messages: The conversation history.
            tools: Optional tool schemas (ignored by echo).
            tool_choice: Optional tool selection control (ignored by echo).
        """
        self.call_count += 1
        last = messages[-1]
        content = last.content if hasattr(last, "content") else str(last)
        return AIMessage(content=f"{self._prefix}{content}")
