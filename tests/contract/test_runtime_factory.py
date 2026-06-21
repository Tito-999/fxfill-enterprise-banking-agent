"""Contract tests for runtime factory."""

from __future__ import annotations

import pytest

from fxfill_banking_agent.auth import AuthorizationGateway, AutoApprovePolicy
from fxfill_banking_agent.config import AgentConfig
from fxfill_banking_agent.llm import MockLLM
from fxfill_banking_agent.mcp_client import StubMCPClient
from fxfill_banking_agent.runtime_factory import create_runtime


class TestRuntimeFactory:
    @pytest.mark.asyncio
    async def test_creates_runtime_with_explicit_deps(self) -> None:
        config = AgentConfig()
        llm = MockLLM()
        mcp = StubMCPClient()
        auth = AuthorizationGateway(policy=AutoApprovePolicy())
        runtime = await create_runtime(config=config, llm=llm, mcp_client=mcp, auth_gateway=auth)
        assert runtime is not None
        assert runtime.llm is llm
        assert runtime.mcp_client is mcp

    @pytest.mark.asyncio
    async def test_fails_without_llm(self) -> None:
        config = AgentConfig()
        mcp = StubMCPClient()
        auth = AuthorizationGateway(policy=AutoApprovePolicy())
        with pytest.raises(RuntimeError):
            await create_runtime(config=config, llm=None, mcp_client=mcp, auth_gateway=auth)

    @pytest.mark.asyncio
    async def test_fails_without_mcp(self) -> None:
        config = AgentConfig()
        llm = MockLLM()
        auth = AuthorizationGateway(policy=AutoApprovePolicy())
        with pytest.raises(RuntimeError):
            await create_runtime(config=config, llm=llm, mcp_client=None, auth_gateway=auth)
