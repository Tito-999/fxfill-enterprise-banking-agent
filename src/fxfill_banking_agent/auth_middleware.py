"""Authentication middleware (A8 + B6).

Extracts TrustedRequestContext from verified tokens (OIDC/JWT in prod,
development headers in dev). Populates request.state.context for downstream
use by the agent runtime.

Never trusts client-controlled body fields for identity.
"""

from __future__ import annotations

from typing import Any, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from fxfill_banking_agent.security.context import ANONYMOUS_CONTEXT, TrustedRequestContext


class AuthMiddleware(BaseHTTPMiddleware):
    """Extracts trusted identity from request and populates request.state.

    Development mode: reads X-User-Id, X-Tenant-Id headers.
    Production mode: validates OIDC JWT Bearer token.

    Never trusts the request body for identity fields.
    """

    def __init__(
        self,
        app: Any,
        *,
        production_mode: bool = False,
        oidc_issuer: str = "",
        oidc_audience: str = "",
    ) -> None:
        super().__init__(app)
        self._production = production_mode
        self._issuer = oidc_issuer
        self._audience = oidc_audience

    async def dispatch(  # type: ignore[override]
        self, request: Request, call_next: Callable[..., Any]
    ) -> Response:
        if self._production:
            context = await self._resolve_production(request)
        else:
            context = self._resolve_development(request)

        request.state.trusted_context = context
        return await call_next(request)

    def _resolve_development(self, request: Request) -> TrustedRequestContext:
        """Development: read identity from headers (NOT for production)."""
        return TrustedRequestContext(
            subject_id=request.headers.get("X-User-Id", "default"),
            tenant_id=request.headers.get("X-Tenant-Id", "default"),
            roles=frozenset(request.headers.get("X-User-Roles", "customer").split(",")),
            auth_session_id=request.headers.get("X-Session-Id", ""),
            request_id=getattr(request.state, "correlation_id", ""),
            source="development-header",
        )

    async def _resolve_production(self, request: Request) -> TrustedRequestContext:
        """Production: validate OIDC JWT Bearer token.

        This is a scaffold. Real implementation must:
        1. Extract Bearer token from Authorization header
        2. Validate signature against OIDC issuer's JWKS
        3. Check exp, nbf, iss, aud claims
        4. Extract sub, tenant, roles from claims
        5. Return TrustedRequestContext
        """
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return ANONYMOUS_CONTEXT

        # Placeholder: real JWT validation goes here
        return TrustedRequestContext(
            subject_id="authenticated-user",
            tenant_id="default",
            source="oidc",
        )


def get_trusted_context(request: Request) -> TrustedRequestContext:
    """Extract the TrustedRequestContext from a request.

    Must be called after AuthMiddleware has processed the request.
    """
    return getattr(request.state, "trusted_context", ANONYMOUS_CONTEXT)
