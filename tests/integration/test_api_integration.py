"""Integration tests: FastAPI → AgentRuntime."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from fxfill_banking_agent.agent import AgentRuntime
from fxfill_banking_agent.api import create_app
from fxfill_banking_agent.auth import AuthorizationGateway, AutoApprovePolicy
from fxfill_banking_agent.llm import MockLLM
from fxfill_banking_agent.mcp_client import StubMCPClient


@pytest.fixture
def api_client() -> TestClient:
    llm = MockLLM([AIMessage(content="Hello! Your balance is $500.")])
    mcp = StubMCPClient()
    app = create_app(llm=llm, mcp_client=mcp)
    return TestClient(app)


class TestAPIAgentIntegration:
    def test_health(self, api_client: TestClient) -> None:
        resp = api_client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_agent_request(self, api_client: TestClient) -> None:
        resp = api_client.post("/agent", json={"message": "balance?"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["answer"] == "Hello! Your balance is $500."

    def test_session_id_roundtrip(self, api_client: TestClient) -> None:
        resp = api_client.post("/agent", json={"message": "hi", "session_id": "s42"})
        assert resp.status_code == 200
        assert resp.json()["session_id"] == "s42"


@pytest.fixture
def auth_api_client() -> TestClient:
    llm = MockLLM([AIMessage(content="ok")])
    mcp = StubMCPClient()
    auth = AuthorizationGateway(policy=AutoApprovePolicy())
    app = create_app(llm=llm, mcp_client=mcp, auth_gateway=auth)
    return TestClient(app)


class TestAPIAuthIntegration:
    def test_authorized_request_passes(self, auth_api_client: TestClient) -> None:
        resp = auth_api_client.post("/agent", json={"message": "test"})
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_persistence_integration(tmp_path) -> None:
    """SqliteEventStore can be wired into AgentRuntime."""
    from fxfill_banking_agent.persistence import SqliteEventStore

    db_path = tmp_path / "test.db"
    store = SqliteEventStore(db_path)
    await store.connect()

    llm = MockLLM([AIMessage(content="Hello!")])
    mcp = StubMCPClient()
    runtime = AgentRuntime(llm=llm, mcp_client=mcp, event_store=store)
    result = await runtime.run("test")
    assert result["final_answer"] == "Hello!"

    # Events were persisted
    events = await store.query_run(result.get("session_id", ""))
    # User message event should be persisted
    assert len(events) >= 1

    await store.close()
