"""Tests for the FastAPI banking agent service."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from fxfill_banking_agent.api import create_app
from fxfill_banking_agent.llm import MockLLM
from fxfill_banking_agent.mcp_client import StubMCPClient


@pytest.fixture
def client() -> TestClient:
    """Create a test client with a mock agent."""
    llm = MockLLM([AIMessage(content="Hello! Your balance is $500.")])
    mcp = StubMCPClient()
    app = create_app(llm=llm, mcp_client=mcp)
    return TestClient(app)


class TestHealthEndpoint:
    def test_health_returns_ok(self, client: TestClient) -> None:
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["version"] in ("0.1.0", "0.2.0")


class TestAgentEndpoint:
    def test_agent_returns_answer(self, client: TestClient) -> None:
        response = client.post("/agent", json={"message": "What is my balance?"})
        assert response.status_code == 200
        data = response.json()
        assert "answer" in data
        assert data["answer"] == "Hello! Your balance is $500."
        assert data["step_count"] >= 0

    def test_agent_with_session_id(self, client: TestClient) -> None:
        response = client.post("/agent", json={"message": "hello", "session_id": "sess-42"})
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == "sess-42"

    def test_empty_message_rejected(self, client: TestClient) -> None:
        response = client.post("/agent", json={"message": ""})
        assert response.status_code == 422  # validation error

    def test_too_long_message_rejected(self, client: TestClient) -> None:
        response = client.post("/agent", json={"message": "x" * 10001})
        assert response.status_code == 422

    def test_missing_message_rejected(self, client: TestClient) -> None:
        response = client.post("/agent", json={})
        assert response.status_code == 422


class TestAgentErrorHandling:
    def test_app_compiles_and_health_works(self) -> None:
        """App with default auth policy compiles and serves health."""
        from fxfill_banking_agent.api import create_app

        llm = MockLLM([AIMessage(content="ok")])
        app = create_app(llm=llm, mcp_client=StubMCPClient())
        client = TestClient(app)
        response = client.get("/health")
        assert response.status_code == 200
