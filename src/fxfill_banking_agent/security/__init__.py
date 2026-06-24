"""Security module — trusted identity, authentication, and authorization.

This module provides:

- ``TrustedRequestContext``: Immutable identity container populated by
  authentication middleware, never by model-generated arguments.
- Authentication resolvers for extracting identity from request context.
- Identity-aware authorization policies.
"""

from fxfill_banking_agent.security.context import TrustedRequestContext

__all__ = ["TrustedRequestContext"]
