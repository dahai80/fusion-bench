"""Tests for auth identity + API Key resolution."""

from __future__ import annotations

import pytest

from fusion_bench.auth.identity import Identity
from fusion_bench.auth.rbac import RBACStore, Role


class TestIdentity:
    def test_identity_fields(self):
        ident = Identity(user_id="u1", workspace_id="ws1", role=Role.ADMIN, source="apikey", scopes=["task:create"])
        assert ident.user_id == "u1"
        assert ident.role == Role.ADMIN
        assert ident.source == "apikey"
        assert ident.scopes == ["task:create"]


class TestApiKeyStore:
    def test_create_and_verify_api_key(self, tmp_path):
        store = RBACStore(db_path=tmp_path / "rbac.db")
        key = store.create_api_key("alice", "operator")
        assert isinstance(key, str) and len(key) >= 32
        ident = store.verify_api_key(key)
        assert ident is not None
        assert ident.user_id == "alice"
        assert ident.role == Role.OPERATOR
        assert ident.source == "apikey"
        assert ident.workspace_id == "default"
        store.close()

    def test_verify_unknown_key_returns_none(self, tmp_path):
        store = RBACStore(db_path=tmp_path / "rbac.db")
        assert store.verify_api_key("bogus-key") is None
        store.close()

    def test_revoke_api_key(self, tmp_path):
        store = RBACStore(db_path=tmp_path / "rbac.db")
        key = store.create_api_key("bob", "viewer")
        assert store.revoke_api_key(key) is True
        assert store.verify_api_key(key) is None
        assert store.revoke_api_key("missing") is False
        store.close()

    def test_list_api_keys_hides_secret(self, tmp_path):
        store = RBACStore(db_path=tmp_path / "rbac.db")
        key = store.create_api_key("carol", "admin", workspace_id="team1")
        rows = store.list_api_keys()
        assert len(rows) == 1
        assert rows[0]["user_id"] == "carol"
        assert rows[0]["workspace_id"] == "team1"
        assert rows[0]["revoked"] == 0
        assert "api_key" not in rows[0]  # secret never returned in list
        store.close()

    def test_api_key_last_used_updated(self, tmp_path):
        store = RBACStore(db_path=tmp_path / "rbac.db")
        key = store.create_api_key("dave", "operator")
        store.verify_api_key(key)
        rows = store.list_api_keys()
        assert rows[0]["last_used"] is not None
        store.close()


import os
from unittest.mock import AsyncMock, patch

import pytest


class TestOAuthResolver:
    def _make_resolver(self, monkeypatch, tmp_path, jwks_url="http://idp/jwks", issuer="idp", audience="fb"):
        monkeypatch.setenv("FUSION_BENCH_OAUTH_JWKS_URL", jwks_url)
        monkeypatch.setenv("FUSION_BENCH_OAUTH_ISSUER", issuer)
        monkeypatch.setenv("FUSION_BENCH_OAUTH_AUDIENCE", audience)
        monkeypatch.setenv("FUSION_BENCH_OAUTH_ROLE_CLAIM", "roles")
        from fusion_bench.auth.identity import OAuthResolver
        return OAuthResolver()

    @pytest.mark.asyncio
    async def test_valid_token_resolves_identity(self, monkeypatch, tmp_path):
        resolver = self._make_resolver(monkeypatch, tmp_path)
        with patch.object(resolver, "_verify_jwt", new=AsyncMock(return_value={"sub": "user42", "roles": ["admin"], "workspace_id": "ws9"})):
            ident = await resolver.resolve("valid.jwt.token")
        assert ident is not None
        assert ident.user_id == "user42"
        assert ident.role.value == "admin"
        assert ident.workspace_id == "ws9"
        assert ident.source == "oauth"

    @pytest.mark.asyncio
    async def test_expired_token_returns_none(self, monkeypatch, tmp_path):
        resolver = self._make_resolver(monkeypatch, tmp_path)
        with patch.object(resolver, "_verify_jwt", new=AsyncMock(return_value=None)):
            assert await resolver.resolve("expired.jwt") is None

    @pytest.mark.asyncio
    async def test_unknown_role_claim_falls_back_to_viewer(self, monkeypatch, tmp_path):
        resolver = self._make_resolver(monkeypatch, tmp_path)
        with patch.object(resolver, "_verify_jwt", new=AsyncMock(return_value={"sub": "u1", "roles": ["unknown_role"]})):
            ident = await resolver.resolve("tok")
        assert ident is not None
        assert ident.role == Role.VIEWER

    @pytest.mark.asyncio
    async def test_missing_sub_returns_none(self, monkeypatch, tmp_path):
        resolver = self._make_resolver(monkeypatch, tmp_path)
        with patch.object(resolver, "_verify_jwt", new=AsyncMock(return_value={"roles": ["admin"]})):
            assert await resolver.resolve("tok") is None

    def test_disabled_when_no_jwks_url(self, monkeypatch):
        monkeypatch.delenv("FUSION_BENCH_OAUTH_JWKS_URL", raising=False)
        from fusion_bench.auth.identity import OAuthResolver
        resolver = OAuthResolver()
        assert resolver.enabled is False
