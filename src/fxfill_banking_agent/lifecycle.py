"""Explicit application resource ownership and lifecycle.

ApplicationResources owns every app-managed resource and provides
idempotent, isolated shutdown. The FastAPI lifespan calls
``resources.close()``; bootstrap uses it for rollback on partial failure.
"""

from __future__ import annotations

from typing import Any

from fxfill_banking_agent.grant_repo import GrantRepository
from fxfill_banking_agent.hitl_store import SqliteHITLStore
from fxfill_banking_agent.idempotency_store import SqliteIdempotencyStore
from fxfill_banking_agent.logging import get_logger
from fxfill_banking_agent.mcp.client import MCPClientAdapter
from fxfill_banking_agent.persistence import SqliteEventStore

logger = get_logger(__name__)


class ApplicationResources:
    """Owns every app-managed resource with idempotent, isolated shutdown.

    Resources owned when configured as app-owned:
    - SqliteHITLStore
    - GrantRepository
    - SqliteIdempotencyStore
    - SqliteEventStore
    - LLM provider (any object with ``close()``)
    - MCP client (any object with ``disconnect()``)
    """

    def __init__(
        self,
        *,
        hitl_store: SqliteHITLStore | None = None,
        grant_repo: GrantRepository | None = None,
        idempotency_store: SqliteIdempotencyStore | None = None,
        event_store: SqliteEventStore | None = None,
        llm_provider: Any = None,
        mcp_client: MCPClientAdapter | Any = None,
    ) -> None:
        self.hitl_store = hitl_store
        self.grant_repo = grant_repo
        self.idempotency_store = idempotency_store
        self.event_store = event_store
        self.llm_provider = llm_provider
        self.mcp_client = mcp_client
        self._closed = False

    async def close(self) -> None:
        """Idempotent shutdown — each resource closed at most once.

        A failure closing one resource is logged but does not stop
        remaining cleanup.
        """
        if self._closed:
            return
        self._closed = True

        # ── SQLite stores ──────────────────────────────────────────
        for store in (
            self.hitl_store,
            self.grant_repo,
            self.idempotency_store,
            self.event_store,
        ):
            if store is not None and hasattr(store, "close"):
                try:
                    await store.close()
                except Exception:
                    logger.warning(
                        "resource_close_failed",
                        resource=type(store).__name__,
                        exc_info=True,
                    )

        # ── LLM provider ───────────────────────────────────────────
        if self.llm_provider is not None and hasattr(self.llm_provider, "close"):
            try:
                await self.llm_provider.close()
            except Exception:
                logger.warning(
                    "provider_close_failed",
                    error="provider.close() raised",
                    exc_info=True,
                )

        # ── MCP client ─────────────────────────────────────────────
        if self.mcp_client is not None and hasattr(self.mcp_client, "disconnect"):
            try:
                await self.mcp_client.disconnect()
            except Exception:
                logger.warning(
                    "mcp_disconnect_failed",
                    error="mcp.disconnect() raised",
                    exc_info=True,
                )
