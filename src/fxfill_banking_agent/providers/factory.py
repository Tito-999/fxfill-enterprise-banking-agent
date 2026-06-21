"""Provider factory — constructs LLM providers from configuration."""

from __future__ import annotations

import os

from fxfill_banking_agent.llm import LLMProvider
from fxfill_banking_agent.providers.base import ProviderConfig


def create_provider(config: ProviderConfig | None = None) -> LLMProvider:
    """Create an LLM provider from configuration.

    Args:
        config: Provider configuration. Uses defaults if omitted.

    Returns:
        A configured LLMProvider.

    Raises:
        RuntimeError: If the required token environment variable is
            not set and no credential provider is available.
    """
    cfg = config or ProviderConfig()

    if cfg.provider_type == "deepseek":
        from fxfill_banking_agent.providers.deepseek import DeepSeekProvider

        token = os.environ.get(cfg.token_env_var, "")
        if not token:
            raise RuntimeError(
                f"DeepSeek provider requires {cfg.token_env_var} environment variable. "
                f"Set it or configure a different provider."
            )
        return DeepSeekProvider(
            config=cfg,
            token=token,
        )

    raise RuntimeError(f"Unknown provider type: {cfg.provider_type!r}")
