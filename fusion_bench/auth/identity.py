"""Identity model + resolution middleware for API authentication."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

import httpx
import jwt
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from .rbac import RBACStore, Role

logger = logging.getLogger(__name__)


@dataclass
class Identity:
    user_id: str
    workspace_id: str = "default"
    role: Role = Role.VIEWER
    source: str = "anonymous"
    scopes: list[str] = field(default_factory=list)

    @property
    def is_anonymous(self) -> bool:
        return self.source == "anonymous"


class OAuthResolver:
    # Verifies JWT bearer tokens against an external IdP JWKS endpoint.

    def __init__(self) -> None:
        self.jwks_url = os.environ.get("FUSION_BENCH_OAUTH_JWKS_URL", "")
        self.issuer = os.environ.get("FUSION_BENCH_OAUTH_ISSUER", "")
        self.audience = os.environ.get("FUSION_BENCH_OAUTH_AUDIENCE", "")
        self.role_claim = os.environ.get("FUSION_BENCH_OAUTH_ROLE_CLAIM", "roles")
        self._jwks_keys: dict[str, str] = {}

    @property
    def enabled(self) -> bool:
        return bool(self.jwks_url)

    async def _verify_jwt(self, token: str) -> dict | None:
        if not self.enabled:
            return None
        try:
            unverified_header = jwt.get_unverified_header(token)
            kid = unverified_header.get("kid")
            key = await self._get_key(kid)
            if key is None:
                logger.warning("OAuth: no JWKS key for kid=%s", kid)
                return None
            payload = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                audience=self.audience or None,
                issuer=self.issuer or None,
                options={"require": ["exp", "iat"]},
            )
            return payload
        except jwt.PyJWTError as e:
            logger.warning("OAuth token verify failed: %s", e)
            return None
        except Exception as e:
            logger.error("OAuth verify error: %s", e)
            return None

    async def _get_key(self, kid: str | None) -> str | None:
        if kid and kid in self._jwks_keys:
            return self._jwks_keys[kid]
        if not self.jwks_url:
            return None
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(self.jwks_url)
                resp.raise_for_status()
                for k in resp.json().get("keys", []):
                    self._jwks_keys[k["kid"]] = jwt.algorithms.RSAAlgorithm.from_jwk(k)
                return self._jwks_keys.get(kid) if kid else None
        except Exception as e:
            logger.error("JWKS fetch failed: %s", e)
            return None

    async def resolve(self, token: str) -> Identity | None:
        payload = await self._verify_jwt(token)
        if not payload:
            return None
        sub = payload.get("sub")
        if not sub:
            logger.warning("OAuth token missing sub claim")
            return None
        role_values = payload.get(self.role_claim, [])
        if isinstance(role_values, str):
            role_values = [role_values]
        role = Role.VIEWER
        for rv in role_values:
            try:
                role = Role(rv)
                break
            except ValueError:
                continue
        workspace_id = payload.get("workspace_id", "default")
        return Identity(
            user_id=sub,
            workspace_id=workspace_id,
            role=role,
            source="oauth",
            scopes=payload.get("scope", "").split() if isinstance(payload.get("scope"), str) else [],
        )


class IdentityMiddleware(BaseHTTPMiddleware):
    # Resolves request identity via X-API-Key or Bearer token, else anonymous.

    async def dispatch(self, request: Request, call_next):
        identity = Identity(user_id="anonymous", role=Role.VIEWER, source="anonymous")
        api_key_enabled = os.environ.get("FUSION_BENCH_API_KEY_ENABLED", "1") != "0"
        oauth_enabled = os.environ.get("FUSION_BENCH_OAUTH_ENABLED", "0") == "1"

        api_key = request.headers.get("x-api-key", "")
        if api_key_enabled and api_key:
            store = RBACStore()
            try:
                resolved = store.verify_api_key(api_key)
                if resolved:
                    identity = resolved
            finally:
                store.close()

        if identity.is_anonymous and oauth_enabled:
            auth = request.headers.get("authorization", "")
            if auth.lower().startswith("bearer "):
                token = auth[7:].strip()
                resolver = OAuthResolver()
                if resolver.enabled:
                    resolved = await resolver.resolve(token)
                    if resolved:
                        identity = resolved

        request.state.identity = identity
        return await call_next(request)
