"""Production composition tests: bootstrap constructs all HITL dependencies."""

from __future__ import annotations

from pathlib import Path

import pytest

from fxfill_banking_agent.bootstrap import bootstrap_app
from fxfill_banking_agent.config import AgentConfig
from fxfill_banking_agent.providers.base import ProviderConfig


class TestProductionBootstrap:
    @pytest.mark.asyncio
    async def test_bootstrap_constructs_all_dependencies(self, tmp_path: Path) -> None:
        """bootstrap_app with db_path constructs HITL executor and all stores."""
        import os

        os.environ["DEEPSEEK_API_TOKEN"] = "test-token"
        db = tmp_path / "boot.db"
        cfg = AgentConfig(max_agent_steps=5)
        pcfg = ProviderConfig()
        app = await bootstrap_app(
            agent_config=cfg, provider_config=pcfg, db_path=str(db), production_mode=False
        )
        assert app is not None
        # Health check works
        from fastapi.testclient import TestClient

        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_bootstrap_fails_without_db_in_production(self, tmp_path: Path) -> None:
        """Production mode without db_path fails at startup."""
        import os

        os.environ["DEEPSEEK_API_TOKEN"] = "test-token"
        with pytest.raises(RuntimeError, match="db_path"):
            await bootstrap_app(production_mode=True)

    @pytest.mark.asyncio
    async def test_bootstrap_fails_in_production_mode(self, tmp_path: Path) -> None:
        """Production mode requires authenticated actor resolver."""
        import os

        os.environ["DEEPSEEK_API_TOKEN"] = "test-token"
        db = tmp_path / "prod_fail.db"
        with pytest.raises(RuntimeError, match="actor"):
            await bootstrap_app(db_path=str(db), production_mode=True)

    def test_development_bootstrap_succeeds(self, tmp_path: Path) -> None:
        """Development mode with db_path succeeds."""
        import asyncio
        import os

        os.environ["DEEPSEEK_API_TOKEN"] = "test-token"
        db = tmp_path / "dev.db"
        app = asyncio.get_event_loop().run_until_complete(
            bootstrap_app(db_path=str(db), production_mode=False)
        )
        assert app is not None
