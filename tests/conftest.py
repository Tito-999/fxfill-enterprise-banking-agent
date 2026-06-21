"""Shared test fixtures — patches constructors so tests auto-inject
AuthorizationGateway (with AutoApprovePolicy) where production code
would require explicit injection. Production code always fails closed."""

from __future__ import annotations

import pytest

from fxfill_banking_agent.auth import AuthorizationGateway, AutoApprovePolicy


@pytest.fixture(autouse=True)
async def _close_sqlite_connections():
    """Close all tracked SQLite connections after each test."""
    yield
    from fxfill_banking_agent.db import close_all_connections

    await close_all_connections()


# ── Patch AuthorizationGateway to allow no-arg construction in tests ──
_original_auth_init = AuthorizationGateway.__init__


def _patched_auth_init(self, policy=None):
    if policy is None:
        policy = AutoApprovePolicy()
    _original_auth_init(self, policy=policy)


AuthorizationGateway.__init__ = _patched_auth_init


# ── Patch create_app, AgentRuntime, and graph ───────────────────────
def _install_all_patches():
    # Patch api.create_app
    from fxfill_banking_agent import api

    _orig_create = api.create_app

    def _patched_create(*a, **kw):
        if not kw.get("auth_gateway"):
            kw["auth_gateway"] = AuthorizationGateway(policy=AutoApprovePolicy())
        # Auto-inject executor for HITL-enabled tests
        if not kw.get("approval_executor") and kw.get("hitl_store") and kw.get("grant_repo"):
            # Create executor with test deps (creates temp DB stores)
            pass  # Too complex — let tests provide executors explicitly
        return _orig_create(*a, **kw)

    api.create_app = _patched_create

    # Patch agent.AgentRuntime.__init__
    from fxfill_banking_agent import agent

    _orig_ar_init = agent.AgentRuntime.__init__

    def _patched_ar_init(self, *a, **kw):
        if not kw.get("auth_gateway"):
            kw["auth_gateway"] = AuthorizationGateway(policy=AutoApprovePolicy())
        _orig_ar_init(self, *a, **kw)

    agent.AgentRuntime.__init__ = _patched_ar_init

    # Patch graph._require_deps
    from fxfill_banking_agent import graph as g

    _orig_require = g._require_deps

    def _patched_require(config):
        cfg = config.get("configurable", {})
        if "auth_gateway" not in cfg:
            cfg["auth_gateway"] = AuthorizationGateway(policy=AutoApprovePolicy())
            config["configurable"] = cfg
        return _orig_require(config)

    g._require_deps = _patched_require


_install_all_patches()
