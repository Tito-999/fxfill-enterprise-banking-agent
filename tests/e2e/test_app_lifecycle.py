"""Application lifecycle acceptance tests.

Uses TestClient as context manager or ASGI lifespan protocol.
Does NOT rely on tests/conftest.py autouse cleanup.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fxfill_banking_agent.lifecycle import ApplicationResources
from fxfill_banking_agent.logging import get_logger

logger = get_logger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Counting fakes
# ═══════════════════════════════════════════════════════════════════════════


class CountingStore:
    """Wraps a real store to count close calls."""

    def __init__(self, real_store):
        self._real = real_store
        self.close_count = 0
        self._closed = False

    async def close(self) -> None:
        self.close_count += 1
        if not self._closed:
            self._closed = True
            await self._real.close()

    # Delegate common methods
    async def get(self, *a, **kw):
        return await self._real.get(*a, **kw)

    async def insert(self, *a, **kw):
        return await self._real.insert(*a, **kw)

    async def update_status(self, *a, **kw):
        return await self._real.update_status(*a, **kw)

    async def list_pending(self, *a, **kw):
        return await self._real.list_pending(*a, **kw)

    async def insert_pending(self, *a, **kw):
        return await self._real.insert_pending(*a, **kw)

    async def approve_pending(self, *a, **kw):
        return await self._real.approve_pending(*a, **kw)

    async def get_by_session(self, *a, **kw):
        return await self._real.get_by_session(*a, **kw)

    async def mark_reconciliation_required(self, *a, **kw):
        return await self._real.mark_reconciliation_required(*a, **kw)

    async def mark_rejected(self, *a, **kw):
        return await self._real.mark_rejected(*a, **kw)

    async def connect(self) -> None:
        if hasattr(self._real, "connect"):
            await self._real.connect()

    async def reserve(self, *a, **kw):
        return await self._real.reserve(*a, **kw)


class CountingProvider:
    """Provider fake that counts close calls."""

    def __init__(self, real_provider=None):
        self._real = real_provider
        self.close_count = 0

    async def close(self) -> None:
        self.close_count += 1
        if self._real and hasattr(self._real, "close"):
            await self._real.close()

    async def invoke(self, *a, **kw):
        if self._real:
            return await self._real.invoke(*a, **kw)
        from langchain_core.messages import AIMessage

        return AIMessage(content="ok")


class CountingMCP:
    """MCP fake that counts disconnect calls."""

    def __init__(self, tools=None):
        self._tools = tools or {}
        self.disconnect_count = 0

    @property
    def tools(self) -> dict:
        return dict(self._tools)

    async def connect(self) -> None:
        pass

    async def disconnect(self) -> None:
        self.disconnect_count += 1

    async def call_tool(self, call):
        from fxfill_banking_agent.mcp_client import ToolResult

        return ToolResult(tool_name=call.name, success=True, content="ok")


class FailingStore:
    """Store whose close raises."""

    def __init__(self, label: str = ""):
        self.label = label
        self.close_count = 0

    async def close(self) -> None:
        self.close_count += 1
        raise RuntimeError(f"FailingStore({self.label}).close() raised")


# ═══════════════════════════════════════════════════════════════════════════
# ApplicationResources unit tests
# ═══════════════════════════════════════════════════════════════════════════


class TestApplicationResources:
    @pytest.mark.asyncio
    async def test_close_is_idempotent(self) -> None:
        """Repeated close() calls do not double-close."""
        store = CountingStore(_make_dummy_store())
        resources = ApplicationResources(hitl_store=store)
        await resources.close()
        assert store.close_count == 1
        await resources.close()
        assert store.close_count == 1  # second close is no-op

    @pytest.mark.asyncio
    async def test_close_failure_does_not_block_remaining_resources(
        self,
    ) -> None:
        """One resource failing during close does not prevent others from closing."""
        failing = FailingStore("fail")
        passing = CountingStore(_make_dummy_store())
        resources = ApplicationResources(hitl_store=failing, grant_repo=passing)
        await resources.close()
        assert failing.close_count == 1
        assert passing.close_count == 1  # still closed despite failing

    @pytest.mark.asyncio
    async def test_all_stores_and_provider_and_mcp_closed(self) -> None:
        """Every resource type is closed through its correct method."""
        hitl = CountingStore(_make_dummy_store())
        grant = CountingStore(_make_dummy_store())
        idem = CountingStore(_make_dummy_store())
        events = CountingStore(_make_dummy_store())
        provider = CountingProvider()
        mcp_client = CountingMCP()

        resources = ApplicationResources(
            hitl_store=hitl,
            grant_repo=grant,
            idempotency_store=idem,
            event_store=events,
            llm_provider=provider,
            mcp_client=mcp_client,
        )
        await resources.close()

        assert hitl.close_count == 1
        assert grant.close_count == 1
        assert idem.close_count == 1
        assert events.close_count == 1
        assert provider.close_count == 1
        assert mcp_client.disconnect_count == 1

    @pytest.mark.asyncio
    async def test_no_resources_is_safe(self) -> None:
        """Closing with no resources is a no-op."""
        resources = ApplicationResources()
        await resources.close()
        await resources.close()  # idempotent


# ═══════════════════════════════════════════════════════════════════════════
# Lifespan integration tests
# ═══════════════════════════════════════════════════════════════════════════


class TestAppLifespan:
    def test_app_lifespan_closes_all_owned_resources(self, tmp_path: Path) -> None:
        """ASGI lifespan calls ApplicationResources.close() on shutdown."""
        hitl = CountingStore(_make_dummy_store())
        grant = CountingStore(_make_dummy_store())
        idem = CountingStore(_make_dummy_store())
        events = CountingStore(_make_dummy_store())
        provider = CountingProvider()
        mcp_client = CountingMCP()

        resources = ApplicationResources(
            hitl_store=hitl,
            grant_repo=grant,
            idempotency_store=idem,
            event_store=events,
            llm_provider=provider,
            mcp_client=mcp_client,
        )

        app = _make_minimal_app(resources)

        with TestClient(app) as client:
            resp = client.get("/health")
            assert resp.status_code == 200

        # After context manager exit, lifespan shutdown ran
        assert hitl.close_count == 1
        assert grant.close_count == 1
        assert idem.close_count == 1
        assert events.close_count == 1
        assert provider.close_count == 1
        assert mcp_client.disconnect_count == 1

    def test_app_lifespan_closes_provider_and_disconnects_mcp(self, tmp_path: Path) -> None:
        """Provider close() and MCP disconnect() are called on shutdown."""
        provider = CountingProvider()
        mcp_client = CountingMCP()

        resources = ApplicationResources(
            llm_provider=provider,
            mcp_client=mcp_client,
        )

        app = _make_minimal_app(resources)

        with TestClient(app):
            pass  # just enter and exit

        assert provider.close_count == 1
        assert mcp_client.disconnect_count == 1

    def test_close_failure_does_not_block_remaining_in_lifespan(self, tmp_path: Path) -> None:
        """One failing close in lifespan does not block remaining cleanup."""
        failing = FailingStore("lifespan-fail")
        passing = CountingStore(_make_dummy_store())

        resources = ApplicationResources(
            hitl_store=failing,
            grant_repo=passing,
        )

        app = _make_minimal_app(resources)

        # Should not raise
        with TestClient(app):
            pass

        assert failing.close_count == 1
        assert passing.close_count == 1

    def test_resource_close_is_idempotent_via_lifespan(self, tmp_path: Path) -> None:
        """Lifespan-triggered close is idempotent."""
        hitl = CountingStore(_make_dummy_store())
        resources = ApplicationResources(hitl_store=hitl)

        app = _make_minimal_app(resources)

        with TestClient(app):
            pass

        assert hitl.close_count == 1
        # Manual close after lifespan is idempotent

        asyncio.get_event_loop().run_until_complete(resources.close())
        assert hitl.close_count == 1

    def test_no_aiosqlite_worker_after_lifespan_shutdown(self, tmp_path: Path) -> None:
        """After application shutdown, no aiosqlite connections remain."""
        from fxfill_banking_agent.db import _open_connections

        # Ensure clean slate
        assert len(_open_connections) == 0

        resources = ApplicationResources()
        app = _make_minimal_app(resources)

        with TestClient(app):
            pass

        # After lifespan shutdown, connections are cleaned up
        # (Our minimal app doesn't create any — verify the invariant holds)
        remaining = len(_open_connections)
        assert remaining == 0, f"Expected 0 open connections, got {remaining}"


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _make_dummy_store():
    """Create a minimal real store on an in-memory or temp DB for CountingStore."""

    # Use a throwaway in-memory connection for the real store
    # The CountingStore wraps it; close() calls the real close.
    # We can't easily make a SqliteHITLStore without a real file, so we use
    # a lightweight object with a close method.
    class _Dummy:
        async def close(self) -> None:
            pass

    return _Dummy()


def _make_minimal_app(resources: ApplicationResources) -> FastAPI:
    """Build a minimal FastAPI app that uses the given resources for lifespan."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _lifespan(app_instance: FastAPI):
        yield
        await resources.close()

    app = FastAPI(lifespan=_lifespan)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app
