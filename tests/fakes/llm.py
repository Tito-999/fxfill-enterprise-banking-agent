"""Test fakes for LLM providers. Re-exports from production source for
backward compatibility while marking these as test-only."""

# Re-export test fakes from production modules.
# These are kept in production source only for backward compatibility
# with existing tests. New tests should import from tests/fakes/.
# bootstrap.py and runtime_factory.py never import these.
from fxfill_banking_agent.llm import EchoLLM, MockLLM  # noqa: F401
