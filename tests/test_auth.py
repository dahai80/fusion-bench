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
