"""Opt-in live provider smoke test.

Excluded from default pytest runs. Requires explicit environment flag.

Usage: LIVE_PROVIDER_TEST=1 uv run pytest tests/contract/test_live_provider.py -v -s -m live_provider
"""

from __future__ import annotations

import os

import pytest

# ── Guards ──────────────────────────────────────────────────────────


def _require_env() -> tuple[str, str]:
    """Return (token, error_message)."""
    if not os.environ.get("LIVE_PROVIDER_TEST") == "1":
        return "", "LIVE_PROVIDER_TEST=1 not set"
    token = os.environ.get("DEEPSEEK_API_TOKEN", "")
    if not token or token == "your-api-key-here":
        return "", "DEEPSEEK_API_TOKEN is not set or still a placeholder"
    return token, ""


# ── Smoke test ──────────────────────────────────────────────────────


@pytest.mark.live_provider
class TestLiveProvider:
    """Minimal smoke test — does not invoke banking write tools."""

    def test_smoke_text_response(self) -> None:
        """Perform a single minimal request to the live provider."""
        token, err = _require_env()
        if err:
            pytest.skip(err)

        import asyncio

        from langchain_core.messages import HumanMessage

        from fxfill_banking_agent.providers.base import ProviderConfig
        from fxfill_banking_agent.providers.deepseek import DeepSeekProvider

        config = ProviderConfig(max_tokens=16, request_timeout=30)
        provider = DeepSeekProvider(config=config, token=token)

        try:
            msg = asyncio.get_event_loop().run_until_complete(
                provider.invoke([HumanMessage(content="Reply exactly with OK")])
            )
            assert msg.content is not None
            assert len(msg.content) > 0
        finally:
            asyncio.get_event_loop().run_until_complete(provider.close())
