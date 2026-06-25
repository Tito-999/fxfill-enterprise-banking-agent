"""OIDC JWT verification (Stage 1.2).

Validates Bearer tokens against configured OIDC issuer.
Supports JWKS key rotation with configurable cache TTL.
Fail-closed: any verification error returns 401.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from fxfill_banking_agent.logging import get_logger
from fxfill_banking_agent.security.context import TrustedRequestContext

logger = get_logger(__name__)

# ── Allowed signing algorithms ───────────────────────────────────────
ALLOWED_ALGORITHMS: frozenset[str] = frozenset(
    {"RS256", "RS384", "RS512", "ES256", "ES384", "ES512"}
)


@dataclass
class TokenClaims:
    """Extracted and validated JWT claims."""

    sub: str = ""
    tenant_id: str = ""
    roles: list[str] = field(default_factory=list)
    scopes: list[str] = field(default_factory=list)
    iss: str = ""
    aud: str = ""
    exp: int = 0
    nbf: int = 0
    iat: int = 0
    jti: str = ""
    sid: str = ""


class OIDCVerifier:
    """Verified OIDC JWT authentication.

    In development mode, falls back to header-based identity.
    In production, requires valid OIDC configuration and verified tokens.

    Args:
        issuer: Expected issuer URL.
        audience: Expected audience.
        jwks_url: JWKS endpoint URL.
        cache_ttl_seconds: JWKS cache time-to-live.
    """

    def __init__(
        self,
        issuer: str = "",
        audience: str = "",
        jwks_url: str = "",
        cache_ttl_seconds: int = 300,
    ) -> None:
        self._issuer = issuer
        self._audience = audience
        self._jwks_url = jwks_url
        self._cache_ttl = cache_ttl_seconds
        self._jwks_cache: dict[str, Any] = {}
        self._jwks_last_fetch: float = 0.0

    async def verify(self, token: str) -> TokenClaims | None:
        """Verify a Bearer token and return claims. Returns None on failure.

        Never raises — always returns None for invalid tokens.
        Never logs the token.
        """
        if not token or not self._issuer:
            return None

        try:
            import jwt as pyjwt
        except ImportError:
            logger.error("oidc_missing_pyjwt")
            return None

        try:
            # Decode header to get kid without verifying signature first
            unverified_header = pyjwt.get_unverified_header(token)
            kid = unverified_header.get("kid")
            alg = unverified_header.get("alg", "")

            # Block dangerous algorithms
            if alg not in ALLOWED_ALGORITHMS:
                logger.warning("oidc_blocked_algorithm", alg=alg)
                return None
            if alg == "none":
                logger.warning("oidc_blocked_none_algorithm")
                return None

            # Fetch JWKS
            jwks = await self._get_jwks()
            if not jwks:
                return None

            # Find key by kid
            key = self._find_key(jwks, kid)
            if key is None:
                logger.warning("oidc_unknown_kid", kid=kid)
                return None

            # Verify signature and claims
            payload = pyjwt.decode(
                token,
                key,
                algorithms=[alg],
                issuer=self._issuer,
                audience=self._audience,
                options={"require": ["exp", "sub", "iss", "aud"]},
            )

            return TokenClaims(
                sub=payload.get("sub", ""),
                tenant_id=payload.get("tenant_id", ""),
                roles=payload.get("roles", []),
                scopes=payload.get("scope", "").split(),
                iss=payload.get("iss", ""),
                aud=payload.get("aud", ""),
                exp=payload.get("exp", 0),
                nbf=payload.get("nbf", 0),
                iat=payload.get("iat", 0),
                jti=payload.get("jti", ""),
                sid=payload.get("sid", ""),
            )

        except pyjwt.ExpiredSignatureError:
            logger.info("oidc_expired_token")
            return None
        except pyjwt.ImmatureSignatureError:
            logger.info("oidc_not_yet_valid")
            return None
        except pyjwt.InvalidIssuerError:
            logger.info("oidc_invalid_issuer")
            return None
        except pyjwt.InvalidAudienceError:
            logger.info("oidc_invalid_audience")
            return None
        except pyjwt.InvalidSignatureError:
            logger.warning("oidc_invalid_signature")
            return None
        except Exception as exc:
            logger.error("oidc_verification_error", error=str(exc)[:200])
            return None

    def claims_to_context(self, claims: TokenClaims, request_id: str = "") -> TrustedRequestContext:
        """Convert verified claims to a TrustedRequestContext."""
        return TrustedRequestContext(
            subject_id=claims.sub,
            tenant_id=claims.tenant_id or "default",
            roles=frozenset(claims.roles),
            scopes=frozenset(claims.scopes),
            auth_session_id=claims.sid,
            token_id=claims.jti,
            issuer=claims.iss,
            request_id=request_id,
            source="oidc",
        )

    async def _get_jwks(self) -> dict[str, Any] | None:
        """Fetch JWKS, with cache."""
        now = time.monotonic()
        if self._jwks_cache and (now - self._jwks_last_fetch) < self._cache_ttl:
            return self._jwks_cache

        if not self._jwks_url:
            return None

        try:
            import urllib.request

            req = urllib.request.Request(
                self._jwks_url,
                headers={"Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                self._jwks_cache = json.loads(resp.read())
                self._jwks_last_fetch = now
                return self._jwks_cache
        except Exception as exc:
            logger.warning("oidc_jwks_fetch_failed", error=str(exc)[:200])
            # Return cached if available even if expired
            return self._jwks_cache if self._jwks_cache else None

    @staticmethod
    def _find_key(jwks: dict[str, Any], kid: str | None) -> Any | None:
        """Find a key by kid in the JWKS."""
        try:
            from jwt import PyJWKClient

            client = PyJWKClient.__new__(PyJWKClient)
            if kid:
                return client.get_signing_key(kid)
            return client
        except Exception:
            pass

        # Manual key lookup as fallback
        keys = jwks.get("keys", [])
        for key_data in keys:
            if kid is None or key_data.get("kid") == kid:
                try:
                    from jwt import PyJWK

                    return PyJWK(key_data).key
                except Exception:
                    continue
        return None


async def build_context_from_token(
    token: str,
    verifier: OIDCVerifier,
    request_id: str = "",
) -> TrustedRequestContext | None:
    """Convenience: verify token and build context in one call."""
    claims = await verifier.verify(token)
    if claims is None:
        return None
    return verifier.claims_to_context(claims, request_id)
