# Release 1 — Identity & Activation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship Release 1 of the enterprise track — real authentication (API Key + OAuth2), Pipeline cache integration, LLM-as-Judge for Agent/Artifact executors, and a fixed Docker build — closing §16 deferred items and unblocking Release 2 multi-tenancy.

**Architecture:** Four independent layers, dependency-ordered. AUTH first (identity foundation), then CACHE and JUDGE (both read auth/env but don't depend on each other), then DOCKER (no code dependency, K8s prerequisite). Each task is TDD: failing test → minimal impl → green → commit.

**Tech Stack:** Python 3.12, FastAPI, httpx (async), SQLite (stdlib `sqlite3`), PyJWT (new dep for OAuth), pytest + pytest-asyncio + pytest-mock. Docker (python:3.12-slim).

**Spec:** `docs/superpowers/specs/2026-08-25-release1-identity-activation-design.md`

## Global Constraints

- Python `>=3.12` (pyproject); base image `python:3.12-slim`.
- Indent: 4-space multiples. No docstrings (repo rule). Inline comments only.
- All modules: `logging.getLogger(__name__)` (repo rule).
- No secrets in code — all auth config via env vars (repo rule).
- Model inference via fusion-mlx HTTP API only — never import MLX/torch/transformers.
- pytest-asyncio `asyncio_mode = "auto"` — async test functions need no marker.
- Default ports: serve=11450, fusion-mlx API=11432.
- Existing `pytest tests/` must stay green after every task.

## File Structure

| File | Responsibility | Action |
|------|----------------|--------|
| `fusion_bench/auth/identity.py` | Identity dataclass, IdentityMiddleware, ApiKeyResolver, OAuthResolver | Create |
| `fusion_bench/auth/rbac.py` | RBACStore (api_keys table + admin methods), require_permission refactor | Modify |
| `fusion_bench/cache.py` | BenchmarkCache (executor_key + WAL + TTL) | Modify |
| `fusion_bench/judge/base.py` | Judge ABC, JudgeInput, JudgeVerdict | Create |
| `fusion_bench/judge/llm_judge.py` | LLMJudge — fusion-mlx HTTP judge | Create |
| `fusion_bench/judge/config.py` | JudgeConfig dataclass | Create |
| `fusion_bench/judge/__init__.py` | get_judge factory | Create |
| `fusion_bench/storage/judge_store.py` | JudgeStore — SQLite CRUD for JudgeConfig | Create |
| `fusion_bench/orchestrator/pipeline.py` | cache integration + determinism helper | Modify |
| `fusion_bench/executors/agent_executor.py` | judge blend in _evaluate_scenario | Modify |
| `fusion_bench/executors/artifact_executor.py` | judge blend in _evaluate_artifact | Modify |
| `fusion_bench/api/app.py` | add IdentityMiddleware, update require_permission guards | Modify |
| `fusion_bench/cli.py` | api-key, cache, judge subcommands | Modify |
| `Dockerfile` | 3.12 + port 11450 + non-root | Modify |
| `docker-compose.yml` | remove NVIDIA, optional fusion-mlx | Modify |
| `scripts/docker_smoke.sh` | build + run --help | Create |
| `tests/test_auth.py` | AUTH tests | Modify/extend |
| `tests/test_cache_integration.py` | CACHE tests | Create |
| `tests/test_judge.py` | JUDGE tests | Create |

---

## Task 1: Auth — Identity dataclass + ApiKeyResolver + api_keys table

**Files:**
- Create: `fusion_bench/auth/identity.py`
- Modify: `fusion_bench/auth/rbac.py` (add `api_keys` table + admin methods to `RBACStore`)
- Test: `tests/test_auth.py` (new)

**Interfaces:**
- Consumes: `Role`, `Permission`, `RBACStore` from `auth/rbac.py`
- Produces: `Identity` dataclass (`user_id: str`, `workspace_id: str`, `role: Role`, `source: str`, `scopes: list[str]`); `RBACStore.create_api_key(user_id, role, workspace_id="default", scopes=None) -> str`; `RBACStore.verify_api_key(api_key) -> Identity | None`; `RBACStore.revoke_api_key(api_key) -> bool`; `RBACStore.list_api_keys() -> list[dict]`

- [ ] **Step 1: Write failing tests**

Create `tests/test_auth.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_auth.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'fusion_bench.auth.identity'`

- [ ] **Step 3: Add `api_keys` table + admin methods to `RBACStore`**

In `fusion_bench/auth/rbac.py`, add to `_ensure_table` (after the `user_roles` CREATE) an `api_keys` table:

```python
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS api_keys (
                api_key TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                workspace_id TEXT NOT NULL DEFAULT 'default',
                role TEXT NOT NULL DEFAULT 'viewer',
                scopes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                last_used REAL,
                revoked INTEGER NOT NULL DEFAULT 0
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS user_roles (
                user_id TEXT PRIMARY KEY,
                role TEXT NOT NULL DEFAULT 'viewer',
                workspace_id TEXT NOT NULL DEFAULT 'default',
                assigned_by TEXT DEFAULT 'system',
                assigned_at TEXT NOT NULL
            )
        """)
```

Note: the existing `user_roles` CREATE must gain the `workspace_id` column. Replace the existing `user_roles` CREATE block in `_ensure_table` with the version above (adds `workspace_id TEXT NOT NULL DEFAULT 'default'`). Existing DBs migrated via `ALTER TABLE user_roles ADD COLUMN workspace_id TEXT NOT NULL DEFAULT 'default'` — add a guard:

```python
        cols = {r[1] for r in self.conn.execute("PRAGMA table_info(user_roles)").fetchall()}
        if "workspace_id" not in cols:
            self.conn.execute("ALTER TABLE user_roles ADD COLUMN workspace_id TEXT NOT NULL DEFAULT 'default'")
```

Add imports at top of rbac.py:

```python
import json
import secrets
```

Add methods to `RBACStore`:

```python
    def create_api_key(self, user_id: str, role: str, workspace_id: str = "default", scopes: list[str] | None = None) -> str:
        key = secrets.token_urlsafe(32)
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        self.conn.execute(
            "INSERT INTO api_keys (api_key, user_id, workspace_id, role, scopes, created_at, revoked) VALUES (?, ?, ?, ?, ?, ?, 0)",
            (key, user_id, workspace_id, role, json.dumps(scopes or []), now),
        )
        self.conn.commit()
        logger.info("API key created for user=%s role=%s workspace=%s", user_id, role, workspace_id)
        return key

    def verify_api_key(self, api_key: str) -> Identity | None:
        row = self.conn.execute(
            "SELECT api_key, user_id, workspace_id, role, scopes FROM api_keys WHERE api_key = ? AND revoked = 0",
            (api_key,),
        ).fetchone()
        if not row:
            return None
        self.conn.execute("UPDATE api_keys SET last_used = ? WHERE api_key = ?", (time.time(), api_key))
        self.conn.commit()
        try:
            role = Role(row["role"])
        except ValueError:
            role = Role.VIEWER
        from .identity import Identity
        return Identity(
            user_id=row["user_id"],
            workspace_id=row["workspace_id"],
            role=role,
            source="apikey",
            scopes=json.loads(row["scopes"]) if row["scopes"] else [],
        )

    def revoke_api_key(self, api_key: str) -> bool:
        cursor = self.conn.execute("UPDATE api_keys SET revoked = 1 WHERE api_key = ?", (api_key,))
        self.conn.commit()
        revoked = cursor.rowcount > 0
        if revoked:
            logger.info("API key revoked (prefix=%s)", api_key[:8])
        return revoked

    def list_api_keys(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT user_id, workspace_id, role, scopes, created_at, last_used, revoked FROM api_keys ORDER BY created_at DESC"
        ).fetchall()
        return [
            {
                "user_id": r["user_id"],
                "workspace_id": r["workspace_id"],
                "role": r["role"],
                "scopes": json.loads(r["scopes"]) if r["scopes"] else [],
                "created_at": r["created_at"],
                "last_used": r["last_used"],
                "revoked": r["revoked"],
            }
            for r in rows
        ]
```

- [ ] **Step 4: Create `fusion_bench/auth/identity.py` with Identity dataclass**

```python
"""Identity model + resolution middleware for API authentication."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .rbac import Role

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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_auth.py -v`
Expected: PASS (all 6 tests)

- [ ] **Step 6: Run full suite to verify no regression**

Run: `pytest tests/ -q`
Expected: PASS (existing tests unaffected)

- [ ] **Step 7: Commit**

```bash
git add fusion_bench/auth/identity.py fusion_bench/auth/rbac.py tests/test_auth.py
git commit -m "feat(auth): Identity dataclass + API Key store with api_keys table"
```

## Task 2: Auth — OAuthResolver + JWKS verify

**Files:**
- Modify: `pyproject.toml` (add `pyjwt[crypto]` dep)
- Modify: `fusion_bench/auth/identity.py` (add `OAuthResolver`)
- Test: `tests/test_auth.py` (extend)

**Interfaces:**
- Consumes: `Identity` from `auth/identity.py`; env vars `FUSION_BENCH_OAUTH_JWKS_URL`, `FUSION_BENCH_OAUTH_ISSUER`, `FUSION_BENCH_OAUTH_AUDIENCE`, `FUSION_BENCH_OAUTH_ROLE_CLAIM`
- Produces: `OAuthResolver` class — `async def resolve(token: str) -> Identity | None`; reads env at init

- [ ] **Step 1: Add PyJWT dependency**

In `pyproject.toml`, add to `dependencies`:

```toml
    "pyjwt[crypto]>=2.8.0",
```

Then install:

```bash
pip install -e ".[test]"
```

- [ ] **Step 2: Write failing tests**

Append to `tests/test_auth.py`:

```python
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_auth.py::TestOAuthResolver -v`
Expected: FAIL — `AttributeError: module 'fusion_bench.auth.identity' has no attribute 'OAuthResolver'`

- [ ] **Step 4: Implement `OAuthResolver` in `fusion_bench/auth/identity.py`**

Append to `identity.py`:

```python
import os
import httpx
import jwt


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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_auth.py::TestOAuthResolver -v`
Expected: PASS (all 5 tests)

- [ ] **Step 6: Run full suite**

Run: `pytest tests/ -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml fusion_bench/auth/identity.py tests/test_auth.py
git commit -m "feat(auth): OAuthResolver with external IdP JWKS verification"
```

## Task 3: Auth — IdentityMiddleware + require_permission refactor

**Files:**
- Modify: `fusion_bench/auth/identity.py` (add `IdentityMiddleware`)
- Modify: `fusion_bench/auth/rbac.py` (refactor `require_permission`)
- Modify: `fusion_bench/api/app.py` (register middleware)
- Test: `tests/test_auth.py` (extend)

**Interfaces:**
- Consumes: `Identity`, `OAuthResolver` (Task 1+2); `RBACStore.verify_api_key` (Task 1); env `FUSION_BENCH_API_KEY_ENABLED`, `FUSION_BENCH_OAUTH_ENABLED`, `FUSION_BENCH_AUTH_STRICT`
- Produces: `IdentityMiddleware` (attaches `request.state.identity`); `require_permission(permission, allow_anonymous=False)` reads `Request`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_auth.py`:

```python
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from fusion_bench.auth.rbac import Permission, require_permission


def _make_app() -> FastAPI:
    app = FastAPI()
    from fusion_bench.auth.identity import IdentityMiddleware
    app.add_middleware(IdentityMiddleware)

    @app.get("/public")
    async def public(_user: str = Depends(require_permission(Permission.TASK_READ, allow_anonymous=True))):
        return {"ok": True}

    @app.post("/write")
    async def write(_user: str = Depends(require_permission(Permission.TASK_CREATE, allow_anonymous=False))):
        return {"ok": True}
    return app


class TestIdentityMiddleware:
    def test_anonymous_can_read_public(self, monkeypatch):
        monkeypatch.setenv("FUSION_BENCH_AUTH_STRICT", "0")
        client = TestClient(_make_app())
        resp = client.get("/public")
        assert resp.status_code == 200

    def test_anonymous_denied_write_strict(self, monkeypatch, tmp_path):
        monkeypatch.setenv("FUSION_BENCH_AUTH_STRICT", "1")
        # point RBAC store at tmp db so create_api_key is deterministic
        monkeypatch.setattr("fusion_bench.auth.rbac._DEFAULT_DB_PATH", tmp_path / "rbac.db")
        client = TestClient(_make_app())
        resp = client.post("/write")
        assert resp.status_code == 403

    def test_anonymous_allowed_write_nonstrict(self, monkeypatch, tmp_path):
        monkeypatch.setenv("FUSION_BENCH_AUTH_STRICT", "0")
        monkeypatch.setattr("fusion_bench.auth.rbac._DEFAULT_DB_PATH", tmp_path / "rbac.db")
        client = TestClient(_make_app())
        resp = client.post("/write")
        assert resp.status_code == 200

    def test_api_key_auth_write(self, monkeypatch, tmp_path):
        monkeypatch.setenv("FUSION_BENCH_AUTH_STRICT", "1")
        db = tmp_path / "rbac.db"
        monkeypatch.setattr("fusion_bench.auth.rbac._DEFAULT_DB_PATH", db)
        store = RBACStore(db_path=db)
        key = store.create_api_key("alice", "operator")
        store.close()
        client = TestClient(_make_app())
        resp = client.post("/write", headers={"X-API-Key": key})
        assert resp.status_code == 200

    def test_revoked_key_denied(self, monkeypatch, tmp_path):
        monkeypatch.setenv("FUSION_BENCH_AUTH_STRICT", "1")
        db = tmp_path / "rbac.db"
        monkeypatch.setattr("fusion_bench.auth.rbac._DEFAULT_DB_PATH", db)
        store = RBACStore(db_path=db)
        key = store.create_api_key("alice", "admin")
        store.revoke_api_key(key)
        store.close()
        client = TestClient(_make_app())
        resp = client.post("/write", headers={"X-API-Key": key})
        assert resp.status_code == 403
```

Add `from fastapi import Depends` to the test file imports.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_auth.py::TestIdentityMiddleware -v`
Expected: FAIL — `require_permission` still uses `user_id="anonymous"` hardcode; middleware absent.

- [ ] **Step 3: Implement `IdentityMiddleware` in `auth/identity.py`**

Append:

```python
import os

from starlette.middleware.base import BaseRequestMiddleware
from starlette.requests import Request

from .rbac import RBACStore, Role


class IdentityMiddleware(BaseRequestMiddleware):
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
```

- [ ] **Step 4: Refactor `require_permission` in `auth/rbac.py`**

Replace the existing `require_permission` (lines 137-149) with:

```python
def require_permission(permission: Permission, allow_anonymous: bool = False):
    # FastAPI dependency: resolves identity from request.state, enforces permission.
    from fastapi import HTTPException, Request, status

    def _check(request: Request) -> str:
        from .identity import Identity
        identity: Identity = getattr(request.state, "identity", None) or Identity(user_id="anonymous")
        if identity.is_anonymous and not allow_anonymous:
            strict = os.environ.get("FUSION_BENCH_AUTH_STRICT", "0") == "1"
            if strict:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Authentication required")
            logger.warning("Anonymous access to write endpoint %s (non-strict mode)", permission.value)
        if not identity.is_anonymous or not allow_anonymous:
            if not has_permission(identity.user_id, permission):
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Permission {permission.value} required")
        return identity.user_id

    return _check
```

Add `import os` to the top of rbac.py imports. Note: `has_permission` is already a module-level function. Keep the existing `RBACStore.has_permission` method (used by stores directly); the module-level `require_permission` now resolves via request.

Also keep a module-level standalone `has_permission(user_id, permission)` if absent — it currently exists as a `RBACStore` method. Add module-level helper:

```python
def has_permission(user_id: str, permission: Permission) -> bool:
    store = RBACStore()
    try:
        return store.has_permission(user_id, permission)
    finally:
        store.close()
```

- [ ] **Step 5: Register middleware in `api/app.py`**

In `api/app.py`, after the existing `app.add_middleware(_TLSRedirectMiddleware)` block (line 71), add:

```python
    from ..auth.identity import IdentityMiddleware
    app.add_middleware(IdentityMiddleware)
    logger.info("Identity middleware registered")
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_auth.py -v`
Expected: PASS (all auth tests)

- [ ] **Step 7: Run full suite**

Run: `pytest tests/ -q`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add fusion_bench/auth/identity.py fusion_bench/auth/rbac.py fusion_bench/api/app.py tests/test_auth.py
git commit -m "feat(auth): IdentityMiddleware + request-aware require_permission"
```

## Task 4: Auth — CLI api-key subcommand + bootstrap

**Files:**
- Modify: `fusion_bench/cli.py` (add `api-key` parser + `cmd_api_key` + dispatch entry)
- Test: `tests/test_cli.py` (extend)

**Interfaces:**
- Consumes: `RBACStore.create_api_key/revoke_api_key/list_api_keys` (Task 1)
- Produces: `fusion-bench api-key create|revoke|list` CLI

- [ ] **Step 1: Write failing tests**

Append to `tests/test_cli.py`:

```python
class TestApiKeyCLI:
    def test_api_key_create_and_list(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr("fusion_bench.auth.rbac._DEFAULT_DB_PATH", tmp_path / "rbac.db")
        import fusion_bench.cli as cli
        from fusion_bench.auth.rbac import RBACStore
        # run create via direct cmd function
        import argparse
        args = argparse.Namespace(command="api-key", action="create", user="alice", role="operator", workspace="default", scopes="")
        cli.cmd_api_key(args)
        out = capsys.readouterr().out
        assert "api_key" in out.lower() or len(out.strip()) >= 32
        # list
        args2 = argparse.Namespace(command="api-key", action="list", user="", role="", workspace="", scopes="")
        cli.cmd_api_key(args2)
        out2 = capsys.readouterr().out
        assert "alice" in out2

    def test_api_key_revoke(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr("fusion_bench.auth.rbac._DEFAULT_DB_PATH", tmp_path / "rbac.db")
        import fusion_bench.cli as cli
        import argparse
        args = argparse.Namespace(command="api-key", action="create", user="bob", role="viewer", workspace="default", scopes="")
        cli.cmd_api_key(args)
        key = capsys.readouterr().out.strip().split()[-1]
        args2 = argparse.Namespace(command="api-key", action="revoke", user="", role="", workspace="", scopes="", key=key)
        cli.cmd_api_key(args2)
        assert "revoked" in capsys.readouterr().out.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cli.py::TestApiKeyCLI -v`
Expected: FAIL — `AttributeError: module 'fusion_bench.cli' has no attribute 'cmd_api_key'`

- [ ] **Step 3: Add `api-key` parser + dispatch + `cmd_api_key`**

In `cli.py`, add the parser (alongside `backup_parser`, before `args = parser.parse_args()`):

```python
    # api-key
    apikey_parser = subparsers.add_parser("api-key", help="Manage API keys")
    apikey_parser.add_argument("action", choices=["create", "revoke", "list"], help="Action")
    apikey_parser.add_argument("--user", default="", help="User ID (create)")
    apikey_parser.add_argument("--role", default="viewer", help="Role: admin|operator|viewer (create)")
    apikey_parser.add_argument("--workspace", default="default", help="Workspace ID (create)")
    apikey_parser.add_argument("--scopes", default="", help="Comma-separated scopes (create)")
    apikey_parser.add_argument("--key", default="", help="API key to revoke (revoke)")
```

Add to `dispatch` dict:

```python
        "api-key": lambda: cmd_api_key(args),
```

Add the handler function (near other `cmd_*` functions):

```python
def cmd_api_key(args):
    import logging
    from .auth.rbac import RBACStore
    log = logging.getLogger(__name__)
    store = RBACStore()
    try:
        if args.action == "create":
            if not args.user:
                print("Error: --user required for create", file=sys.stderr)
                sys.exit(1)
            scopes = [s.strip() for s in args.scopes.split(",") if s.strip()]
            key = store.create_api_key(args.user, args.role, args.workspace, scopes)
            print(key)
            log.info("Created API key for user=%s role=%s", args.user, args.role)
        elif args.action == "revoke":
            if not args.key:
                print("Error: --key required for revoke", file=sys.stderr)
                sys.exit(1)
            if store.revoke_api_key(args.key):
                print(f"revoked: {args.key[:8]}...")
            else:
                print("key not found", file=sys.stderr)
                sys.exit(1)
        elif args.action == "list":
            rows = store.list_api_keys()
            if not rows:
                print("(no API keys)")
            for r in rows:
                print(f"{r['user_id']}\t{r['workspace_id']}\t{r['role']}\trevoked={r['revoked']}\t{r['created_at']}")
    finally:
        store.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_cli.py::TestApiKeyCLI -v`
Expected: PASS

- [ ] **Step 5: Run full suite**

Run: `pytest tests/ -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add fusion_bench/cli.py tests/test_cli.py
git commit -m "feat(auth): api-key CLI subcommand (create/revoke/list)"
```

## Task 5: Cache — BenchmarkCache executor_key + WAL + TTL

**Files:**
- Modify: `fusion_bench/cache.py`
- Test: `tests/test_cache_integration.py` (new — unit portion)

**Interfaces:**
- Consumes: none (leaf)
- Produces: `BenchmarkCache.get(model, config, task, executor_key) -> dict | None`; `set(model, config, task, executor_key, result) -> None`; `__init__(db_path="", ttl_seconds=None)`; WAL mode

- [ ] **Step 1: Write failing tests**

Create `tests/test_cache_integration.py`:

```python
"""Tests for BenchmarkCache executor_key + WAL + TTL."""

from __future__ import annotations

import time

import pytest

from fusion_bench.cache import BenchmarkCache


class TestBenchmarkCacheUnit:
    def test_set_get_with_executor_key(self, tmp_path):
        cache = BenchmarkCache(db_path=str(tmp_path / "cache.db"))
        cache.set("qwen", {"temp": 0}, "mmlu", "speed", {"score": 0.8})
        got = cache.get("qwen", {"temp": 0}, "mmlu", "speed")
        assert got == {"score": 0.8}
        cache.close()

    def test_executor_key_isolation(self, tmp_path):
        cache = BenchmarkCache(db_path=str(tmp_path / "cache.db"))
        cache.set("qwen", {}, "mmlu", "speed", {"score": 0.8})
        cache.set("qwen", {}, "mmlu", "agent", {"score": 0.5})
        assert cache.get("qwen", {}, "mmlu", "speed") == {"score": 0.8}
        assert cache.get("qwen", {}, "mmlu", "agent") == {"score": 0.5}
        cache.close()

    def test_ttl_expiry(self, tmp_path):
        cache = BenchmarkCache(db_path=str(tmp_path / "cache.db"), ttl_seconds=0.5)
        cache.set("qwen", {}, "mmlu", "speed", {"score": 0.8})
        assert cache.get("qwen", {}, "mmlu", "speed") == {"score": 0.8}
        time.sleep(0.6)
        assert cache.get("qwen", {}, "mmlu", "speed") is None
        cache.close()

    def test_no_ttl_never_expires(self, tmp_path):
        cache = BenchmarkCache(db_path=str(tmp_path / "cache.db"), ttl_seconds=None)
        cache.set("qwen", {}, "mmlu", "speed", {"score": 0.8})
        assert cache.get("qwen", {}, "mmlu", "speed") == {"score": 0.8}
        cache.close()

    def test_clear_by_model(self, tmp_path):
        cache = BenchmarkCache(db_path=str(tmp_path / "cache.db"))
        cache.set("qwen", {}, "mmlu", "speed", {"score": 0.8})
        cache.set("llama", {}, "mmlu", "speed", {"score": 0.7})
        assert cache.clear(model="qwen") == 1
        assert cache.get("qwen", {}, "mmlu", "speed") is None
        assert cache.get("llama", {}, "mmlu", "speed") == {"score": 0.7}
        cache.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cache_integration.py::TestBenchmarkCacheUnit -v`
Expected: FAIL — `TypeError: BenchmarkCache.get() takes 3 positional arguments but 4 given` (executor_key not yet in signature)

- [ ] **Step 3: Modify `cache.py` — add executor_key + WAL + TTL**

In `BenchmarkCache.__init__`, add `ttl_seconds` param:

```python
    def __init__(self, db_path: str = "", ttl_seconds: float | None = None):
        if not db_path:
            db_path = str(Path.home() / ".fusion-bench" / "cache.db")
        self.db_path = db_path
        self.ttl_seconds = ttl_seconds
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._init_db()
```

In `_init_db`, add executor_key column + WAL + migration:

```python
    def _init_db(self) -> None:
        with self._cursor() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS benchmarks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    model TEXT NOT NULL,
                    config_json TEXT NOT NULL,
                    task TEXT NOT NULL,
                    executor_key TEXT NOT NULL DEFAULT 'speed',
                    result_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    UNIQUE(model, config_json, task, executor_key)
                );
                CREATE INDEX IF NOT EXISTS idx_benchmarks_lookup
                    ON benchmarks(model, config_json, task, executor_key);
            """)
            cols = {r[1] for r in conn.execute("PRAGMA table_info(benchmarks)").fetchall()}
            if "executor_key" not in cols:
                conn.execute("ALTER TABLE benchmarks ADD COLUMN executor_key TEXT NOT NULL DEFAULT 'speed'")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_benchmarks_lookup ON benchmarks(model, config_json, task, executor_key)")
```

Update `get` to accept executor_key + TTL check:

```python
    def get(self, model: str, config: dict | None, task: str, executor_key: str = "speed") -> dict | None:
        config_json = json.dumps(config or {}, sort_keys=True)
        with self._cursor() as conn:
            row = conn.execute(
                "SELECT result_json, created_at FROM benchmarks WHERE model = ? AND config_json = ? AND task = ? AND executor_key = ?",
                (model, config_json, task, executor_key),
            ).fetchone()
        if not row:
            return None
        if self.ttl_seconds is not None and (time.time() - row["created_at"]) > self.ttl_seconds:
            with self._cursor() as conn:
                conn.execute("DELETE FROM benchmarks WHERE model = ? AND config_json = ? AND task = ? AND executor_key = ?",
                             (model, config_json, task, executor_key))
            return None
        return json.loads(row["result_json"])
```

Update `set`:

```python
    def set(self, model: str, config: dict | None, task: str, executor_key: str, result: dict) -> None:
        config_json = json.dumps(config or {}, sort_keys=True)
        result_json = json.dumps(result, ensure_ascii=False)
        with self._cursor() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO benchmarks
                   (model, config_json, task, executor_key, result_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (model, config_json, task, executor_key, result_json, time.time()),
            )
```

Update `clear` to optionally filter executor_key (keep model/task filters working; executor_key optional). Leave `clear` signature `clear(self, model="", task="")` — executor_key not needed for clear.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_cache_integration.py::TestBenchmarkCacheUnit -v`
Expected: PASS (all 5)

- [ ] **Step 5: Run full suite**

Run: `pytest tests/ -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add fusion_bench/cache.py tests/test_cache_integration.py
git commit -m "feat(cache): executor_key in cache key + WAL + TTL support"
```

## Task 6: Cache — Pipeline integration (determinism gate + query/write)

**Files:**
- Modify: `fusion_bench/orchestrator/pipeline.py` (constructor + `_run_one_with_retry` + helper)
- Test: `tests/test_cache_integration.py` (extend)

**Interfaces:**
- Consumes: `BenchmarkCache.get/set` (Task 5)
- Produces: `Pipeline(cache=..., use_cache=True)`; module helper `_is_deterministic(config: TaskConfig) -> bool`; cache hit skips executor + trace

- [ ] **Step 1: Write failing tests**

Append to `tests/test_cache_integration.py`:

```python
from unittest.mock import AsyncMock, MagicMock

from fusion_bench.core.plugin_base import EvalResult, TaskConfig
from fusion_bench.core.registry import executor_registry
from fusion_bench.orchestrator.pipeline import Pipeline, _is_deterministic


class TestDeterminismGate:
    def test_temp_zero_is_deterministic(self):
        cfg = TaskConfig(task_id="t1", model="m", executor_key="speed", params={"temperature": 0}, max_samples=10)
        assert _is_deterministic(cfg) is True

    def test_temp_nonzero_not_deterministic(self):
        cfg = TaskConfig(task_id="t1", model="m", executor_key="speed", params={"temperature": 0.7}, max_samples=10)
        assert _is_deterministic(cfg) is False

    def test_no_max_samples_not_deterministic(self):
        cfg = TaskConfig(task_id="t1", model="m", executor_key="speed", params={"temperature": 0}, max_samples=None)
        assert _is_deterministic(cfg) is False

    def test_temp_alias_temp(self):
        cfg = TaskConfig(task_id="t1", model="m", executor_key="speed", params={"temp": 0}, max_samples=5)
        assert _is_deterministic(cfg) is True


class TestPipelineCacheIntegration:
    @pytest.mark.asyncio
    async def test_cache_hit_skips_executor(self, tmp_path):
        cache = BenchmarkCache(db_path=str(tmp_path / "cache.db"))
        cache.set("m", {"temperature": 0}, "t1", "speed", {
            "task_id": "t1", "executor_key": "speed", "model": "m", "level": "L1",
            "metric_name": "accuracy", "metric_value": 0.9, "cases": [], "duration_seconds": 0,
            "errors": [], "meta": {}, "failure_category": "", "failure_detail": "", "optimization_hints": [],
        })
        call_count = 0

        class FakeExecutor:
            name = "speed"
            executor_type = "speed"
            async def run(self, config):
                nonlocal call_count
                call_count += 1
                return EvalResult(task_id=config.task_id, executor_key="speed", model="m", metric_value=0.9)
            def is_available(self):
                return True

        executor_registry._items["speed"] = FakeExecutor
        try:
            pipe = Pipeline(cache=cache, use_cache=True)
            tasks = [{"task_id": "t1", "executor_key": "speed", "params": {"temperature": 0}, "max_samples": 10}]
            result = await pipe.run_suite("m", tasks, level="L1")
            assert call_count == 0  # executor never called — cache hit
            assert len(result.task_results) == 1
        finally:
            executor_registry._items.pop("speed", None)
        cache.close()

    @pytest.mark.asyncio
    async def test_non_deterministic_runs_executor(self, tmp_path):
        cache = BenchmarkCache(db_path=str(tmp_path / "cache.db"))

        class FakeExecutor:
            name = "speed"
            executor_type = "speed"
            async def run(self, config):
                return EvalResult(task_id=config.task_id, executor_key="speed", model="m", metric_value=0.5)
            def is_available(self):
                return True

        executor_registry._items["speed"] = FakeExecutor
        try:
            pipe = Pipeline(cache=cache, use_cache=True)
            tasks = [{"task_id": "t1", "executor_key": "speed", "params": {"temperature": 0.7}, "max_samples": 10}]
            await pipe.run_suite("m", tasks, level="L1")
            # non-deterministic → executor ran, nothing cached
            assert cache.get("m", {"temperature": 0.7}, "t1", "speed") is None
        finally:
            executor_registry._items.pop("speed", None)
        cache.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cache_integration.py::TestDeterminismGate tests/test_cache_integration.py::TestPipelineCacheIntegration -v`
Expected: FAIL — `_is_deterministic` undefined; `Pipeline.__init__` has no `cache` param.

- [ ] **Step 3: Add `_is_deterministic` helper + cache params to Pipeline**

At module level in `pipeline.py` (after imports, before `class Pipeline`):

```python
def _is_deterministic(config: TaskConfig) -> bool:
    # Cache only safe when temperature=0, fixed seed, bounded samples.
    params = config.params or {}
    temp = params.get("temperature", params.get("temp", 0))
    if temp not in (0, 0.0):
        return False
    if config.max_samples is None:
        return False
    return True
```

Add import at top of pipeline.py:

```python
from ..cache import BenchmarkCache
```

In `Pipeline.__init__`, add params:

```python
    def __init__(
        self,
        gate_engine: GateEngine | None = None,
        max_concurrent: int = 4,
        trace_callback: Any | None = None,
        max_retries: int = 2,
        checkpoint_dir: str | Path | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        cache: BenchmarkCache | None = None,
        use_cache: bool = True,
    ):
```

In the body, store:

```python
        self.cache = cache
        self.use_cache = use_cache
```

- [ ] **Step 4: Add cache query + write in `_run_one_with_retry`**

In `_run_one_with_retry`, after `config = TaskConfig(...)` is built (after line ~378) and BEFORE the `if not self.circuit_breaker.can_execute(executor_key):` check, insert cache query:

```python
            if self.use_cache and self.cache and _is_deterministic(config):
                cached = self.cache.get(model, config.params, task_id, executor_key)
                if cached:
                    logger.info("Cache hit for task %s executor %s", task_id, executor_key)
                    stream.emit(suite_id, "cache_hit", {"task_id": task_id, "executor_key": executor_key})
                    cached_result = EvalResult(**cached)
                    completed[task_id] = cached_result
                    return cached_result
                logger.debug("Cache miss for task %s", task_id)
```

After the successful executor run, after `self._record_trace(result, TaskStatus.COMPLETED)` (line ~433) and before `completed[task_id] = result`, insert cache write:

```python
                        if self.use_cache and self.cache and _is_deterministic(config):
                            with contextlib.suppress(Exception):
                                self.cache.set(model, config.params, task_id, executor_key, result.to_dict())
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_cache_integration.py -v`
Expected: PASS (all cache tests)

- [ ] **Step 6: Run full suite**

Run: `pytest tests/ -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add fusion_bench/orchestrator/pipeline.py tests/test_cache_integration.py
git commit -m "feat(cache): Pipeline cache integration with determinism gate"
```

## Task 7: Cache — CLI cache subcommand + run flags

**Files:**
- Modify: `fusion_bench/cli.py` (add `cache` parser + `cmd_cache`; add `--no-cache`/`--cache-ttl` to run/suite parsers; thread to Pipeline)
- Test: `tests/test_cli.py` (extend)

**Interfaces:**
- Consumes: `BenchmarkCache.stats/clear` (cache.py); `Pipeline(cache=, use_cache=)` (Task 6)
- Produces: `fusion-bench cache stats|clear [--model X]`; `fusion-bench run --no-cache --cache-ttl 3600`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_cli.py`:

```python
class TestCacheCLI:
    def test_cache_stats_empty(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr("fusion_bench.cache.BenchmarkCache._DEFAULT_DB_PATH", tmp_path / "cache.db")
        import fusion_bench.cli as cli
        import argparse
        args = argparse.Namespace(command="cache", action="stats", model="", task="")
        cli.cmd_cache(args)
        out = capsys.readouterr().out
        assert "0" in out  # total_entries 0

    def test_cache_clear(self, tmp_path, monkeypatch, capsys):
        from fusion_bench.cache import BenchmarkCache
        cache = BenchmarkCache(db_path=str(tmp_path / "cache.db"))
        cache.set("m", {}, "t1", "speed", {"score": 0.8})
        cache.close()
        import fusion_bench.cli as cli
        import argparse
        args = argparse.Namespace(command="cache", action="clear", model="", task="")
        monkeypatch.setattr("fusion_bench.cli.BenchmarkCache", lambda **kw: BenchmarkCache(db_path=str(tmp_path / "cache.db")))
        cli.cmd_cache(args)
        out = capsys.readouterr().out
        assert "1" in out  # cleared 1 entry
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cli.py::TestCacheCLI -v`
Expected: FAIL — `AttributeError: module 'fusion_bench.cli' has no attribute 'cmd_cache'`

- [ ] **Step 3: Add `cache` parser + dispatch + `cmd_cache`**

In `cli.py`, add parser (near `apikey_parser`):

```python
    # cache
    cache_parser = subparsers.add_parser("cache", help="Manage benchmark cache")
    cache_parser.add_argument("action", choices=["stats", "clear"], help="Action")
    cache_parser.add_argument("--model", default="", help="Filter by model (clear)")
    cache_parser.add_argument("--task", default="", help="Filter by task (clear)")
```

Add import near top of cli.py:

```python
from .cache import BenchmarkCache
```

Add dispatch entry:

```python
        "cache": lambda: cmd_cache(args),
```

Add handler:

```python
def cmd_cache(args):
    import logging
    log = logging.getLogger(__name__)
    cache = BenchmarkCache()
    try:
        if args.action == "stats":
            s = cache.stats()
            print(f"total_entries: {s['total_entries']}")
            for m in s.get("models", []):
                print(f"  {m['model']}: {m['cnt']}")
            log.info("Cache stats: %s entries", s["total_entries"])
        elif args.action == "clear":
            count = cache.clear(model=args.model, task=args.task)
            print(f"cleared: {count}")
            log.info("Cleared %s cache entries (model=%s task=%s)", count, args.model, args.task)
    finally:
        cache.close()
```

- [ ] **Step 4: Add `--no-cache`/`--cache-ttl` flags to run + suite parsers**

In `cli.py`, after the existing `run_parser.add_argument` lines, add:

```python
    run_parser.add_argument("--no-cache", action="store_true", help="Disable result cache")
    run_parser.add_argument("--cache-ttl", type=int, default=0, help="Cache TTL seconds (0=forever)")
```

Similarly for `suite_parser` (after its existing args):

```python
    suite_parser.add_argument("--no-cache", action="store_true", help="Disable result cache")
    suite_parser.add_argument("--cache-ttl", type=int, default=0, help="Cache TTL seconds (0=forever)")
```

- [ ] **Step 5: Thread cache flags into Pipeline in `cmd_run` and `cmd_suite`**

In `cmd_run` and `cmd_suite`, where `Pipeline(...)` is constructed, pass cache params. Example for `cmd_run`:

```python
        cache = None if args.no_cache else BenchmarkCache(ttl_seconds=args.cache_ttl or None)
        pipeline = Pipeline(
            gate_engine=gate_engine,
            cache=cache,
            use_cache=not args.no_cache,
        )
```

Apply the same pattern in `cmd_suite` (it also constructs a `Pipeline`). Guard with `getattr(args, "no_cache", False)` in case other commands reuse the function.

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_cli.py::TestCacheCLI -v`
Expected: PASS

- [ ] **Step 7: Run full suite**

Run: `pytest tests/ -q`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add fusion_bench/cli.py tests/test_cli.py
git commit -m "feat(cache): cache CLI subcommand + --no-cache/--cache-ttl run flags"
```

## Task 8: Judge — Judge ABC + JudgeConfig + JudgeStore

**Files:**
- Create: `fusion_bench/judge/__init__.py`
- Create: `fusion_bench/judge/base.py`
- Create: `fusion_bench/judge/config.py`
- Create: `fusion_bench/storage/judge_store.py`
- Test: `tests/test_judge.py` (new — config/store portion)

**Interfaces:**
- Consumes: none (leaf)
- Produces: `Judge` ABC (`async judge(judge_input) -> JudgeVerdict`); `JudgeInput`, `JudgeVerdict` dataclasses; `JudgeConfig` dataclass; `JudgeStore` (`get(name) -> JudgeConfig | None`, `save(name, config)`, `list() -> list[str]`, `delete(name) -> bool`)

- [ ] **Step 1: Write failing tests**

Create `tests/test_judge.py`:

```python
"""Tests for Judge config + store."""

from __future__ import annotations

import pytest

from fusion_bench.judge.config import JudgeConfig
from fusion_bench.storage.judge_store import JudgeStore


class TestJudgeConfig:
    def test_defaults(self):
        cfg = JudgeConfig(judge_model="qwen")
        assert cfg.judge_type == "hybrid"
        assert cfg.weight == 0.5
        assert cfg.temperature == 0
        assert cfg.criteria == []

    def test_to_dict_roundtrip(self):
        cfg = JudgeConfig(judge_model="m", judge_type="llm", weight=0.7, criteria=["correctness"], rubric="strict")
        d = cfg.to_dict()
        assert d["judge_type"] == "llm"
        cfg2 = JudgeConfig.from_dict(d)
        assert cfg2.weight == 0.7
        assert cfg2.criteria == ["correctness"]


class TestJudgeStore:
    def test_save_and_get(self, tmp_path):
        store = JudgeStore(db_path=str(tmp_path / "judge.db"))
        cfg = JudgeConfig(judge_model="qwen", criteria=["helpfulness"])
        store.save("default", cfg)
        got = store.get("default")
        assert got is not None
        assert got.judge_model == "qwen"
        assert got.criteria == ["helpfulness"]
        store.close()

    def test_get_missing_returns_none(self, tmp_path):
        store = JudgeStore(db_path=str(tmp_path / "judge.db"))
        assert store.get("nope") is None
        store.close()

    def test_list_and_delete(self, tmp_path):
        store = JudgeStore(db_path=str(tmp_path / "judge.db"))
        store.save("a", JudgeConfig(judge_model="m1"))
        store.save("b", JudgeConfig(judge_model="m2"))
        names = store.list()
        assert set(names) == {"a", "b"}
        assert store.delete("a") is True
        assert store.get("a") is None
        assert store.delete("missing") is False
        store.close()

    def test_overwrite_on_save(self, tmp_path):
        store = JudgeStore(db_path=str(tmp_path / "judge.db"))
        store.save("x", JudgeConfig(judge_model="old"))
        store.save("x", JudgeConfig(judge_model="new"))
        assert store.get("x").judge_model == "new"
        store.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_judge.py::TestJudgeConfig tests/test_judge.py::TestJudgeStore -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'fusion_bench.judge'`

- [ ] **Step 3: Create `fusion_bench/judge/config.py`**

```python
"""Judge configuration — defines how an LLM-as-judge blends with rule scoring."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class JudgeInput:
    prompt: str
    expected: str | None
    actual: str
    criteria: list[str] = field(default_factory=list)
    rubric: str = ""


@dataclass
class JudgeVerdict:
    score: float
    reasoning: str = ""
    per_criterion: dict[str, float] = field(default_factory=dict)


@dataclass
class JudgeConfig:
    judge_model: str
    judge_type: str = "hybrid"  # llm | rule | hybrid
    weight: float = 0.5
    criteria: list[str] = field(default_factory=list)
    rubric: str = ""
    temperature: float = 0.0

    def to_dict(self) -> dict:
        return {
            "judge_model": self.judge_model,
            "judge_type": self.judge_type,
            "weight": self.weight,
            "criteria": self.criteria,
            "rubric": self.rubric,
            "temperature": self.temperature,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "JudgeConfig":
        return cls(
            judge_model=d["judge_model"],
            judge_type=d.get("judge_type", "hybrid"),
            weight=d.get("weight", 0.5),
            criteria=d.get("criteria", []),
            rubric=d.get("rubric", ""),
            temperature=d.get("temperature", 0.0),
        )
```

- [ ] **Step 4: Create `fusion_bench/judge/base.py`**

```python
"""Judge abstract base class."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from .config import JudgeInput, JudgeVerdict

logger = logging.getLogger(__name__)


class Judge(ABC):
    # Scores model output against criteria. Returns 0-1 score.

    @abstractmethod
    async def judge(self, judge_input: JudgeInput) -> JudgeVerdict: ...
```

- [ ] **Step 5: Create `fusion_bench/judge/__init__.py`**

```python
"""Judge module — LLM-as-Judge scoring for subjective evaluation."""

from __future__ import annotations

from .base import Judge
from .config import JudgeConfig, JudgeInput, JudgeVerdict

__all__ = ["Judge", "JudgeConfig", "JudgeInput", "JudgeVerdict", "get_judge"]


def get_judge(config: JudgeConfig) -> Judge:
    # Factory: LLMJudge serves llm/hybrid. judge_type="rule" has no LLM judge —
    # executor uses rule_score directly and never calls get_judge. Guard fails
    # visibly (Rule 12) if a rule config is passed here by mistake.
    if config.judge_type == "rule":
        raise ValueError("judge_type='rule' has no LLM judge; executor uses rule_score directly")
    from .llm_judge import LLMJudge
    return LLMJudge(config)
```

- [ ] **Step 6: Create `fusion_bench/storage/judge_store.py`**

```python
"""SQLite store for named JudgeConfig definitions."""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path

from ..judge.config import JudgeConfig

logger = logging.getLogger(__name__)

_DEFAULT_DB_PATH = Path.home() / ".fusion-bench" / "judge.db"


class JudgeStore:
    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path) if db_path else _DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._ensure_table()

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
        return self._conn

    def _ensure_table(self) -> None:
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS judge_configs (
                name TEXT PRIMARY KEY,
                config_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        self.conn.commit()

    def save(self, name: str, config: JudgeConfig) -> None:
        import time
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        self.conn.execute(
            "INSERT OR REPLACE INTO judge_configs (name, config_json, created_at) VALUES (?, ?, ?)",
            (name, json.dumps(config.to_dict(), ensure_ascii=False), now),
        )
        self.conn.commit()
        logger.info("JudgeConfig saved: %s", name)

    def get(self, name: str) -> JudgeConfig | None:
        row = self.conn.execute("SELECT config_json FROM judge_configs WHERE name = ?", (name,)).fetchone()
        if not row:
            return None
        return JudgeConfig.from_dict(json.loads(row["config_json"]))

    def list(self) -> list[str]:
        rows = self.conn.execute("SELECT name FROM judge_configs ORDER BY name").fetchall()
        return [r["name"] for r in rows]

    def delete(self, name: str) -> bool:
        cursor = self.conn.execute("DELETE FROM judge_configs WHERE name = ?", (name,))
        self.conn.commit()
        return cursor.rowcount > 0

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest tests/test_judge.py::TestJudgeConfig tests/test_judge.py::TestJudgeStore -v`
Expected: PASS (all 6)

- [ ] **Step 8: Run full suite**

Run: `pytest tests/ -q`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add fusion_bench/judge/ fusion_bench/storage/judge_store.py tests/test_judge.py
git commit -m "feat(judge): JudgeConfig + JudgeStore + Judge ABC"
```

## Task 9: Judge — LLMJudge (fusion-mlx HTTP + JSON parse + fallback)

**Files:**
- Create: `fusion_bench/judge/llm_judge.py`
- Test: `tests/test_judge.py` (extend — LLMJudge tests)

**Interfaces:**
- Consumes: `Judge` ABC + `JudgeInput`/`JudgeVerdict`/`JudgeConfig` (Task 8)
- Produces: `LLMJudge(Judge)` — `async judge(judge_input: JudgeInput) -> JudgeVerdict`; constructor `LLMJudge(config: JudgeConfig, base_url: str = "http://localhost:11432/v1")`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_judge.py`:

```python
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from fusion_bench.judge import get_judge
from fusion_bench.judge.config import JudgeConfig, JudgeInput
from fusion_bench.judge.llm_judge import LLMJudge


def _mock_response(content: str) -> httpx.Response:
    request = MagicMock(spec=httpx.Request)
    return httpx.Response(
        status_code=200,
        request=request,
        json={"choices": [{"message": {"content": content}}]},
    )


class TestLLMJudge:
    @pytest.mark.asyncio
    async def test_parse_valid_json(self):
        cfg = JudgeConfig(judge_model="qwen", judge_type="llm")
        judge = LLMJudge(cfg)
        content = '{"score": 0.8, "reasoning": "mostly correct"}'
        with patch("fusion_bench.judge.llm_judge.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=_mock_response(content))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client
            verdict = await judge.judge(JudgeInput(prompt="p", expected="e", actual="a", criteria=["correctness"]))
        assert verdict.score == 0.8
        assert "mostly correct" in verdict.reasoning

    @pytest.mark.asyncio
    async def test_parse_malformed_fallback_neutral(self):
        cfg = JudgeConfig(judge_model="qwen", judge_type="llm")
        judge = LLMJudge(cfg)
        with patch("fusion_bench.judge.llm_judge.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=_mock_response("not json at all"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client
            verdict = await judge.judge(JudgeInput(prompt="p", expected="e", actual="a"))
        assert verdict.score == 0.5
        assert verdict.reasoning != ""

    @pytest.mark.asyncio
    async def test_timeout_fallback_neutral(self):
        cfg = JudgeConfig(judge_model="qwen", judge_type="llm")
        judge = LLMJudge(cfg)
        with patch("fusion_bench.judge.llm_judge.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timed out"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client
            verdict = await judge.judge(JudgeInput(prompt="p", expected="e", actual="a"))
        assert verdict.score == 0.5

    @pytest.mark.asyncio
    async def test_score_clamped_to_unit_interval(self):
        cfg = JudgeConfig(judge_model="qwen", judge_type="llm")
        judge = LLMJudge(cfg)
        content = '{"score": 1.5, "reasoning": "over"}'
        with patch("fusion_bench.judge.llm_judge.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=_mock_response(content))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client
            verdict = await judge.judge(JudgeInput(prompt="p", expected="e", actual="a"))
        assert verdict.score == 1.0

    def test_get_judge_factory_llm(self):
        cfg = JudgeConfig(judge_model="qwen", judge_type="llm")
        judge = get_judge(cfg)
        assert isinstance(judge, LLMJudge)

    def test_get_judge_factory_rule_raises(self):
        cfg = JudgeConfig(judge_model="qwen", judge_type="rule")
        with pytest.raises(ValueError):
            get_judge(cfg)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_judge.py::TestLLMJudge -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'fusion_bench.judge.llm_judge'`

- [ ] **Step 3: Create `fusion_bench/judge/llm_judge.py`**

```python
"""LLM-as-Judge — calls fusion-mlx /chat/completions, parses JSON verdict."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx

from .base import Judge
from .config import JudgeConfig, JudgeInput, JudgeVerdict

logger = logging.getLogger(__name__)

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
_NEUTRAL_SCORE = 0.5


def _extract_json(content: str) -> dict[str, Any] | None:
    # Try fenced block first, then raw JSON object, then whole-string parse.
    m = _JSON_FENCE_RE.search(content)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    try:
        return json.loads(content.strip())
    except json.JSONDecodeError:
        pass
    start = content.find("{")
    end = content.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(content[start : end + 1])
        except json.JSONDecodeError:
            pass
    return None


class LLMJudge(Judge):
    # Scores output via fusion-mlx LLM call. Deterministic at temperature=0.

    def __init__(self, config: JudgeConfig, base_url: str = "http://localhost:11432/v1"):
        self.config = config
        self.base_url = base_url.rstrip("/")

    async def judge(self, judge_input: JudgeInput) -> JudgeVerdict:
        prompt = self._build_prompt(judge_input)
        try:
            content = await self._call_llm(prompt)
            parsed = _extract_json(content)
            if not parsed:
                logger.warning("Judge parse failure; neutral fallback. raw=%s", content[:200])
                return JudgeVerdict(score=_NEUTRAL_SCORE, reasoning="judge parse failure; neutral fallback")
            score = float(parsed.get("score", _NEUTRAL_SCORE))
            score = max(0.0, min(1.0, score))
            reasoning = str(parsed.get("reasoning", ""))
            per_criterion = {}
            raw_pc = parsed.get("per_criterion", {})
            if isinstance(raw_pc, dict):
                for k, v in raw_pc.items():
                    try:
                        per_criterion[str(k)] = max(0.0, min(1.0, float(v)))
                    except (TypeError, ValueError):
                        continue
            return JudgeVerdict(score=score, reasoning=reasoning, per_criterion=per_criterion)
        except (httpx.TimeoutException, httpx.HTTPError) as e:
            logger.warning("Judge LLM call failed: %s; neutral fallback", e)
            return JudgeVerdict(score=_NEUTRAL_SCORE, reasoning=f"judge call failed: {e}")
        except Exception as e:
            # Never crash a suite on judge error (spec failure handling).
            logger.error("Judge unexpected error: %s; neutral fallback", e)
            return JudgeVerdict(score=_NEUTRAL_SCORE, reasoning=f"judge error: {e}")

    def _build_prompt(self, judge_input: JudgeInput) -> str:
        criteria_text = ", ".join(judge_input.criteria) if judge_input.criteria else "overall quality"
        parts = [
            "You are an impartial judge. Score the response.",
            f"Prompt: {judge_input.prompt}",
        ]
        if judge_input.expected is not None:
            parts.append(f"Expected: {judge_input.expected}")
        parts.append(f"Actual: {judge_input.actual}")
        parts.append(f"Criteria: {criteria_text}")
        if judge_input.rubric:
            parts.append(f"Rubric: {judge_input.rubric}")
        parts.append('Respond ONLY with JSON: {"score": <0.0-1.0>, "reasoning": "<brief>"}')
        return "\n".join(parts)

    async def _call_llm(self, prompt: str) -> str:
        messages = [
            {"role": "system", "content": "You are an evaluation judge. Output valid JSON only."},
            {"role": "user", "content": prompt},
        ]
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                json={
                    "model": self.config.judge_model,
                    "messages": messages,
                    "max_tokens": 512,
                    "temperature": self.config.temperature,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("choices", [{}])[0].get("message", {}).get("content", "")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_judge.py::TestLLMJudge -v`
Expected: PASS (all 6)

- [ ] **Step 5: Run full suite**

Run: `pytest tests/ -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add fusion_bench/judge/llm_judge.py tests/test_judge.py
git commit -m "feat(judge): LLMJudge fusion-mlx HTTP + JSON parse + neutral fallback"
```

## Task 10: Judge — Agent executor blend

**Files:**
- Modify: `fusion_bench/executors/agent_executor.py` (lines 327-365, `_evaluate_scenario`)
- Test: `tests/test_judge.py` (extend — Agent integration)

**Interfaces:**
- Consumes: `get_judge` + `JudgeStore` + `JudgeInput`/`JudgeVerdict`/`JudgeConfig` (Task 8-9); existing `TrajectoryScorer.score` + `_eval_response` (unchanged)
- Produces: `_evaluate_scenario` now reads `task_config.params.get("judge")` (JudgeConfig name), resolves via `JudgeStore`, blends per `judge_type`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_judge.py`:

```python
from fusion_bench.core.plugin_base import TaskConfig
from fusion_bench.executors.agent_executor import AgentExecutor
from fusion_bench.storage.judge_store import JudgeStore


class TestAgentJudgeBlend:
    @pytest.mark.asyncio
    async def test_hybrid_blend_applies_judge(self, tmp_path, monkeypatch):
        # Seed a hybrid judge config; mock the judge call to a fixed verdict.
        store = JudgeStore(db_path=str(tmp_path / "j.db"))
        store.save("hybrid-j", JudgeConfig(judge_model="qwen", judge_type="hybrid", weight=0.5))
        monkeypatch.setattr("fusion_bench.executors.agent_executor.JudgeStore", lambda *a, **k: store)

        async def fake_judge(judge_input):
            from fusion_bench.judge.config import JudgeVerdict
            return JudgeVerdict(score=1.0, reasoning="perfect")

        monkeypatch.setattr("fusion_bench.judge.get_judge", lambda cfg: type("J", (), {"judge": fake_judge})())

        executor = AgentExecutor()
        cfg = TaskConfig(
            task_id="t", model="qwen", params={"scenarios": [], "judge": "hybrid-j"},
        )
        # _evaluate_scenario directly with one minimal scenario.
        from fusion_bench.executors.agent_executor import AgentScenario
        scenario = AgentScenario(scenario_id="s1", instruction="hi", expected_behavior="x", max_turns=1)
        # Force rule scores to known values by stubbing the multi-turn + rule eval.
        async def fake_turns(sc, tc):
            from fusion_bench.executors.agent_executor import TurnRecord
            return [TurnRecord(turn=0, role="assistant", content="done")]
        monkeypatch.setattr(executor, "_run_multi_turn", fake_turns)
        monkeypatch.setattr(executor, "_eval_response", lambda sc, resp: {"score": 0.0, "passed": False, "details": {}})
        result = await executor._evaluate_scenario(scenario, cfg)
        # rule_score = 0.5*0 + 0.5*0 = 0.0 (criteria 0, traj 0). hybrid = 0.5*1.0 + 0.5*0 = 0.5
        assert abs(result.score - 0.5) < 1e-6
        store.close()

    @pytest.mark.asyncio
    async def test_no_judge_param_unchanged(self, monkeypatch):
        # No judge key -> pure rule scoring, zero behavior change.
        executor = AgentExecutor()
        from fusion_bench.executors.agent_executor import AgentScenario, TurnRecord
        scenario = AgentScenario(scenario_id="s1", instruction="hi", expected_behavior="x", max_turns=1)
        async def fake_turns(sc, tc):
            return [TurnRecord(turn=0, role="assistant", content="done")]
        monkeypatch.setattr(executor, "_run_multi_turn", fake_turns)
        monkeypatch.setattr(executor, "_eval_response", lambda sc, resp: {"score": 0.8, "passed": True, "details": {}})
        cfg = TaskConfig(task_id="t", model="qwen", params={"scenarios": []})
        result = await executor._evaluate_scenario(scenario, cfg)
        # rule_score = 0.5*0.8 + 0.5*0 = 0.4
        assert abs(result.score - 0.4) < 1e-6
        assert result.meta.get("judge_source") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_judge.py::TestAgentJudgeBlend -v`
Expected: FAIL — `_evaluate_scenario` does not yet call judge; meta lacks `judge_source`; score is pure rule.

- [ ] **Step 3: Modify `_evaluate_scenario` in `agent_executor.py`**

Add imports at top (after existing imports, around line 25):

```python
from fusion_bench.judge import get_judge
from fusion_bench.judge.config import JudgeInput
from fusion_bench.storage.judge_store import JudgeStore
```

Replace the score-blend block inside `_evaluate_scenario` (lines 337-354). The current block:

```python
            criteria_eval = self._eval_response(scenario, final_response)
            traj = TrajectoryScorer.score(turns, scenario)
            combined_score = 0.5 * criteria_eval["score"] + 0.5 * traj["trajectory_score"]
            passed = combined_score >= 0.5
            return CaseResult(
                input_text=scenario.instruction,
                expected=scenario.expected_behavior,
                actual=final_response[:500],
                score=combined_score,
                passed=passed,
                latency_ms=latency,
                meta={
                    "scenario_id": scenario.scenario_id,
                    "turns": len(turns),
                    "trajectory": traj,
                    **criteria_eval["details"],
                },
            )
```

Becomes:

```python
            criteria_eval = self._eval_response(scenario, final_response)
            traj = TrajectoryScorer.score(turns, scenario)
            rule_score = 0.5 * criteria_eval["score"] + 0.5 * traj["trajectory_score"]
            final_score, judge_source, judge_meta = await self._apply_judge(scenario, final_response, rule_score, task_config)
            passed = final_score >= 0.5
            meta = {
                "scenario_id": scenario.scenario_id,
                "turns": len(turns),
                "trajectory": traj,
                **criteria_eval["details"],
            }
            if judge_source:
                meta["judge_source"] = judge_source
                meta.update(judge_meta)
            return CaseResult(
                input_text=scenario.instruction,
                expected=scenario.expected_behavior,
                actual=final_response[:500],
                score=final_score,
                passed=passed,
                latency_ms=latency,
                meta=meta,
            )
```

Add the new helper method on `AgentExecutor` (after `_eval_response`, end of class):

```python
    async def _apply_judge(
        self,
        scenario: AgentScenario,
        final_response: str,
        rule_score: float,
        task_config: TaskConfig,
    ) -> tuple[float, str | None, dict]:
        # Returns (final_score, judge_source, judge_meta). judge_source None = no judge.
        judge_name = task_config.params.get("judge")
        if not judge_name:
            return rule_score, None, {}
        store = JudgeStore()
        judge_config = store.get(judge_name)
        store.close()
        if judge_config is None:
            logger.warning("JudgeConfig '%s' not found; rule-only scoring", judge_name)
            return rule_score, None, {}
        if judge_config.judge_type == "rule":
            return rule_score, "rule", {}
        try:
            judge = get_judge(judge_config)
            verdict = await judge.judge(
                JudgeInput(
                    prompt=scenario.instruction,
                    expected=scenario.expected_final_answer or scenario.expected_behavior,
                    actual=final_response,
                    criteria=judge_config.criteria,
                    rubric=judge_config.rubric,
                )
            )
        except Exception as e:
            logger.warning("judge_fallback for scenario %s: %s", scenario.scenario_id, e)
            return rule_score, "fallback", {"judge_fallback": str(e)}
        weight = judge_config.weight
        if judge_config.judge_type == "llm":
            final = verdict.score
        else:  # hybrid
            final = weight * verdict.score + (1 - weight) * rule_score
        return final, judge_config.judge_type, {"judge_score": verdict.score, "judge_reasoning": verdict.reasoning}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_judge.py::TestAgentJudgeBlend -v`
Expected: PASS (both)

- [ ] **Step 5: Run full suite**

Run: `pytest tests/ -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add fusion_bench/executors/agent_executor.py tests/test_judge.py
git commit -m "feat(judge): Agent executor hybrid/llm/rule blend integration"
```

## Task 11: Judge — Artifact executor blend

**Files:**
- Modify: `fusion_bench/executors/artifact_executor.py` (lines 165-194, `_evaluate_artifact`)
- Test: `tests/test_judge.py` (extend — Artifact integration)

**Interfaces:**
- Consumes: `get_judge` + `JudgeStore` + `JudgeInput` (Task 8-9); existing `_eval_artifact` rule check (unchanged)
- Produces: `_evaluate_artifact` now reads `task_config.params.get("judge")`, blends per `judge_type`; adds `meta["judge_source"]`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_judge.py`:

```python
from fusion_bench.executors.artifact_executor import ArtifactExecutor, ArtifactTestCase, ArtifactCriteria


class TestArtifactJudgeBlend:
    @pytest.mark.asyncio
    async def test_hybrid_blend_applies_judge(self, tmp_path, monkeypatch):
        store = JudgeStore(db_path=str(tmp_path / "j.db"))
        store.save("art-j", JudgeConfig(judge_model="qwen", judge_type="hybrid", weight=0.5))
        monkeypatch.setattr("fusion_bench.executors.artifact_executor.JudgeStore", lambda *a, **k: store)

        async def fake_judge(judge_input):
            return JudgeVerdict(score=1.0, reasoning="good")
        monkeypatch.setattr("fusion_bench.judge.get_judge", lambda cfg: type("J", (), {"judge": fake_judge})())

        executor = ArtifactExecutor()
        tc = ArtifactTestCase(
            test_id="t1", artifact_type="json", prompt="make config",
            criteria=[ArtifactCriteria(name="valid_json", description="x", auto_check="json_valid")],
            min_length=5,
        )
        cfg = TaskConfig(task_id="t", model="qwen", params={"judge": "art-j"})
        # Force artifact generation + rule eval to known values.
        async def fake_gen(test_case, task_config):
            return '{"host": "x"}'
        monkeypatch.setattr(executor, "_generate_artifact", fake_gen)
        monkeypatch.setattr(executor, "_eval_artifact", lambda tc, art: {"score": 0.0, "passed": False, "details": {}})
        result = await executor._evaluate_artifact(tc, cfg)
        # rule 0.0, judge 1.0, hybrid weight 0.5 -> 0.5*1.0 + 0.5*0 = 0.5
        assert abs(result.score - 0.5) < 1e-6
        assert result.meta.get("judge_source") == "hybrid"
        store.close()

    @pytest.mark.asyncio
    async def test_no_judge_param_unchanged(self, monkeypatch):
        executor = ArtifactExecutor()
        tc = ArtifactTestCase(test_id="t1", artifact_type="json", prompt="p", min_length=5)
        async def fake_gen(test_case, task_config):
            return '{"a": 1}'
        monkeypatch.setattr(executor, "_generate_artifact", fake_gen)
        monkeypatch.setattr(executor, "_eval_artifact", lambda tc, art: {"score": 0.7, "passed": True, "details": {"k": True}})
        cfg = TaskConfig(task_id="t", model="qwen", params={})
        result = await executor._evaluate_artifact(tc, cfg)
        assert abs(result.score - 0.7) < 1e-6
        assert result.meta.get("judge_source") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_judge.py::TestArtifactJudgeBlend -v`
Expected: FAIL — `_evaluate_artifact` does not yet call judge; score stays at rule value; meta lacks `judge_source`.

- [ ] **Step 3: Modify `_evaluate_artifact` in `artifact_executor.py`**

Add imports at top (after existing imports, around line 17):

```python
from fusion_bench.judge import get_judge
from fusion_bench.judge.config import JudgeInput
from fusion_bench.storage.judge_store import JudgeStore
```

Replace the body of `_evaluate_artifact` (lines 165-194). Current:

```python
    async def _evaluate_artifact(
        self,
        test_case: ArtifactTestCase,
        task_config: TaskConfig,
    ) -> CaseResult:
        t0 = time.time()
        try:
            artifact = await self._generate_artifact(test_case, task_config)
            latency = (time.time() - t0) * 1000
            eval_result = self._eval_artifact(test_case, artifact)
            return CaseResult(
                input_text=test_case.prompt,
                expected=f"{test_case.artifact_type} artifact",
                actual=artifact[:500],
                score=eval_result["score"],
                passed=eval_result["passed"],
                latency_ms=latency,
                meta={"test_id": test_case.test_id, **eval_result["details"]},
            )
        except Exception as e:
            logger.error("Artifact test %s failed: %s", test_case.test_id, e)
            return CaseResult(
                input_text=test_case.prompt,
                expected=f"{test_case.artifact_type} artifact",
                actual=str(e),
                score=0.0,
                passed=False,
                latency_ms=(time.time() - t0) * 1000,
                meta={"test_id": test_case.test_id, "error": str(e)},
            )
```

Becomes:

```python
    async def _evaluate_artifact(
        self,
        test_case: ArtifactTestCase,
        task_config: TaskConfig,
    ) -> CaseResult:
        t0 = time.time()
        try:
            artifact = await self._generate_artifact(test_case, task_config)
            latency = (time.time() - t0) * 1000
            eval_result = self._eval_artifact(test_case, artifact)
            rule_score = eval_result["score"]
            final_score, judge_source, judge_meta = await self._apply_judge(test_case, artifact, rule_score, task_config)
            meta = {"test_id": test_case.test_id, **eval_result["details"]}
            if judge_source:
                meta["judge_source"] = judge_source
                meta.update(judge_meta)
            passed = final_score >= 0.6 and eval_result["details"].get("min_length_check", True)
            return CaseResult(
                input_text=test_case.prompt,
                expected=f"{test_case.artifact_type} artifact",
                actual=artifact[:500],
                score=final_score,
                passed=passed,
                latency_ms=latency,
                meta=meta,
            )
        except Exception as e:
            logger.error("Artifact test %s failed: %s", test_case.test_id, e)
            return CaseResult(
                input_text=test_case.prompt,
                expected=f"{test_case.artifact_type} artifact",
                actual=str(e),
                score=0.0,
                passed=False,
                latency_ms=(time.time() - t0) * 1000,
                meta={"test_id": test_case.test_id, "error": str(e)},
            )

    async def _apply_judge(
        self,
        test_case: ArtifactTestCase,
        artifact: str,
        rule_score: float,
        task_config: TaskConfig,
    ) -> tuple[float, str | None, dict]:
        # Returns (final_score, judge_source, judge_meta). judge_source None = no judge.
        judge_name = task_config.params.get("judge")
        if not judge_name:
            return rule_score, None, {}
        store = JudgeStore()
        judge_config = store.get(judge_name)
        store.close()
        if judge_config is None:
            logger.warning("JudgeConfig '%s' not found; rule-only scoring", judge_name)
            return rule_score, None, {}
        if judge_config.judge_type == "rule":
            return rule_score, "rule", {}
        try:
            judge = get_judge(judge_config)
            verdict = await judge.judge(
                JudgeInput(
                    prompt=test_case.prompt,
                    expected=f"{test_case.artifact_type} artifact meeting criteria",
                    actual=artifact,
                    criteria=judge_config.criteria or [c.name for c in test_case.criteria],
                    rubric=judge_config.rubric,
                )
            )
        except Exception as e:
            logger.warning("judge_fallback for artifact %s: %s", test_case.test_id, e)
            return rule_score, "fallback", {"judge_fallback": str(e)}
        weight = judge_config.weight
        if judge_config.judge_type == "llm":
            final = verdict.score
        else:  # hybrid
            final = weight * verdict.score + (1 - weight) * rule_score
        return final, judge_config.judge_type, {"judge_score": verdict.score, "judge_reasoning": verdict.reasoning}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_judge.py::TestArtifactJudgeBlend -v`
Expected: PASS (both)

- [ ] **Step 5: Run full suite**

Run: `pytest tests/ -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add fusion_bench/executors/artifact_executor.py tests/test_judge.py
git commit -m "feat(judge): Artifact executor hybrid/llm/rule blend integration"
```

## Task 12: Judge — CLI judge subcommand

**Files:**
- Modify: `fusion_bench/cli.py` (add `judge` subparser + `cmd_judge`)
- Test: `tests/test_cli_judge.py` (new)

**Interfaces:**
- Consumes: `JudgeStore` + `JudgeConfig` (Task 8)
- Produces: `fusion-bench judge create|list|show|delete` CLI surface

- [ ] **Step 1: Write failing tests**

Create `tests/test_cli_judge.py`:

```python
"""Tests for the `fusion-bench judge` CLI subcommand."""

from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

from fusion_bench import cli as cli_mod


def _run_cli(argv: list[str], tmp_path):
    db = tmp_path / "judge.db"
    with patch.dict(os.environ, {"FUSION_BENCH_JUDGE_DB": str(db)}):
        return cli_mod.main(argv)


class TestJudgeCLI:
    def test_create_then_list_then_show(self, tmp_path, capsys):
        rc = _run_cli(
            ["judge", "create", "--name", "default", "--model", "qwen", "--type", "hybrid", "--weight", "0.6", "--criteria", "correctness,helpfulness"],
            tmp_path,
        )
        assert rc == 0
        out = capsys.readouterr().out
        assert "default" in out

        rc = _run_cli(["judge", "list"], tmp_path)
        assert rc == 0
        out = capsys.readouterr().out
        assert "default" in out

        rc = _run_cli(["judge", "show", "--name", "default"], tmp_path)
        assert rc == 0
        out = capsys.readouterr().out
        assert "qwen" in out
        assert "hybrid" in out

    def test_delete(self, tmp_path, capsys):
        _run_cli(["judge", "create", "--name", "todelete", "--model", "m"], tmp_path)
        capsys.readouterr()
        rc = _run_cli(["judge", "delete", "--name", "todelete"], tmp_path)
        assert rc == 0
        out = capsys.readouterr().out
        assert "deleted" in out.lower()
        rc = _run_cli(["judge", "show", "--name", "todelete"], tmp_path)
        # show of missing config should report not-found, not crash.
        assert rc == 0

    def test_create_defaults(self, tmp_path, capsys):
        rc = _run_cli(["judge", "create", "--name", "d", "--model", "m"], tmp_path)
        assert rc == 0
        out = capsys.readouterr().out
        assert "hybrid" in out  # default judge_type
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cli_judge.py -v`
Expected: FAIL — `error: invalid choice: 'judge'` (subparser not yet registered)

- [ ] **Step 3: Add `judge` subparser and `cmd_judge` to `cli.py`**

In the subparser-registration section (where other subcommands like `cache` are registered, e.g. after the `cache` parser block), add:

```python
    judge_parser = subparsers.add_parser("judge", help="Manage LLM-as-Judge configs")
    judge_sub = judge_parser.add_subparsers(dest="judge_action", required=True)

    j_create = judge_sub.add_parser("create", help="Create or overwrite a judge config")
    j_create.add_argument("--name", required=True)
    j_create.add_argument("--model", required=True, help="Judge model name")
    j_create.add_argument("--type", default="hybrid", choices=["llm", "rule", "hybrid"])
    j_create.add_argument("--weight", type=float, default=0.5)
    j_create.add_argument("--criteria", default="", help="Comma-separated criteria names")
    j_create.add_argument("--rubric", default="")
    j_create.add_argument("--temperature", type=float, default=0.0)

    judge_sub.add_parser("list", help="List judge configs")

    j_show = judge_sub.add_parser("show", help="Show a judge config")
    j_show.add_argument("--name", required=True)

    j_delete = judge_sub.add_parser("delete", help="Delete a judge config")
    j_delete.add_argument("--name", required=True)
```

In the dispatch dict (where `cmd_cache` etc. are mapped), add:

```python
    "judge": cmd_judge,
```

Add the handler function (near `cmd_cache`):

```python
def cmd_judge(args) -> int:
    import os
    from fusion_bench.judge.config import JudgeConfig
    from fusion_bench.storage.judge_store import JudgeStore

    db_path = os.environ.get("FUSION_BENCH_JUDGE_DB")
    store = JudgeStore(db_path=db_path) if db_path else JudgeStore()
    action = args.judge_action
    try:
        if action == "create":
            criteria = [c.strip() for c in args.criteria.split(",") if c.strip()]
            cfg = JudgeConfig(
                judge_model=args.model,
                judge_type=args.type,
                weight=args.weight,
                criteria=criteria,
                rubric=args.rubric,
                temperature=args.temperature,
            )
            store.save(args.name, cfg)
            print(f"Saved judge config: {args.name} (type={cfg.judge_type}, model={cfg.judge_model}, weight={cfg.weight})")
        elif action == "list":
            names = store.list()
            if not names:
                print("No judge configs.")
            else:
                for n in names:
                    print(n)
        elif action == "show":
            cfg = store.get(args.name)
            if cfg is None:
                print(f"Judge config '{args.name}' not found.")
            else:
                print(f"name: {args.name}")
                print(f"model: {cfg.judge_model}")
                print(f"type: {cfg.judge_type}")
                print(f"weight: {cfg.weight}")
                print(f"criteria: {cfg.criteria}")
                print(f"rubric: {cfg.rubric}")
                print(f"temperature: {cfg.temperature}")
        elif action == "delete":
            deleted = store.delete(args.name)
            print(f"Deleted judge config: {args.name}" if deleted else f"Judge config '{args.name}' not found.")
        return 0
    finally:
        store.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_cli_judge.py -v`
Expected: PASS (all 4)

- [ ] **Step 5: Run full suite**

Run: `pytest tests/ -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add fusion_bench/cli.py tests/test_cli_judge.py
git commit -m "feat(judge): CLI judge create/list/show/delete subcommand"
```

## Task 13: Docker — Dockerfile fix

**Files:**
- Modify: `Dockerfile` (full rewrite — base image, port, user, healthcheck)
- Test: `scripts/docker_smoke.sh` (created in Task 14)

**Interfaces:**
- Consumes: pyproject `requires-python >=3.12`; cli.py `serve` default port 11450
- Produces: image that builds on python:3.12-slim, exposes 11450, runs non-root, healthcheck hits :11450

- [ ] **Step 1: Replace `Dockerfile` contents**

Rewrite the entire file to:

```dockerfile
# Fusion-Bench Docker image — Apple Silicon MLX workbench.
# Importers/callers: docker-compose.yml; CI pipeline `docker build`.
# Affected API: no API changes; containerization only.
# Data schema: N/A.

FROM python:3.12-slim

LABEL maintainer="fusion-bench"
LABEL description="Fusion-Bench: MLX model benchmarking and auto-tuning workbench"

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl build-essential && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY fusion_bench/ ./fusion_bench/

RUN pip install --no-cache-dir -e ".[test]"

# Non-root user for production safety.
RUN useradd -m -r fusion && chown -R fusion:fusion /app
USER fusion

# Default serve port (cli.py `serve` default = 11450).
ENV FUSION_BENCH_PORT=11450
EXPOSE 11450

VOLUME ["/home/fusion/.fusion-bench", "/home/fusion/bench"]

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:11450/health || exit 1

ENTRYPOINT ["fusion-bench"]
CMD ["serve", "--host", "0.0.0.0", "--port", "11450"]
```

- [ ] **Step 2: Verify build (Task 14 smoke script runs this)**

This task's verification is the docker build, executed by the smoke script created in Task 14. No standalone verification here — the smoke script in Task 14 is the test.

- [ ] **Step 3: Commit (with Task 14 together)**

Committed together with Task 14 (single coherent Docker fix commit).

## Task 14: Docker — compose fix + smoke script

**Files:**
- Modify: `docker-compose.yml` (remove NVIDIA GPU block, fix fusion-mlx, add env placeholders)
- Create: `scripts/docker_smoke.sh`

**Interfaces:**
- Consumes: Dockerfile from Task 13 (port 11450, non-root)
- Produces: compose that runs on Apple Silicon (no GPU passthrough); `scripts/docker_smoke.sh` for CI verification

- [ ] **Step 1: Replace `docker-compose.yml` contents**

Rewrite the entire file to:

```yaml
# Fusion-Bench + Fusion-MLX docker-compose (Apple Silicon).
# Importers/callers: `docker-compose up`; DevOps deployment.
# Affected API: no API changes; orchestration only.
# Data schema: N/A.
#
# fusion-mlx runs on Metal (Apple Silicon) — no GPU passthrough in containers.
# On an Apple Silicon host run fusion-mlx natively via start.sh and set
# FUSION_MLX_URL=http://host.docker.internal:11432/v1. The fusion-mlx service
# below is optional (CPU image, non-Apple CI); uncomment for CI-only use.

services:
  fusion-bench:
    build: .
    container_name: fusion-bench
    ports:
      - "11450:11450"
    volumes:
      - fusion-bench-data:/home/fusion/.fusion-bench
      - fusion-bench-tasks:/home/fusion/bench
    environment:
      # Point at host fusion-mlx on macOS Docker Desktop.
      - FUSION_MLX_URL=http://host.docker.internal:11432/v1
      - FUSION_BENCH_LOG_LEVEL=INFO
      # Post-R1 AUTH config (enable when IdP configured):
      # - FUSION_BENCH_OAUTH_ENABLED=0
      # - FUSION_BENCH_OAUTH_JWKS_URL=
      # - FUSION_BENCH_OAUTH_ISSUER=
      # - FUSION_BENCH_OAUTH_AUDIENCE=
    restart: unless-stopped

  # OPTIONAL: CPU-only fusion-mlx for non-Apple CI. Disabled by default — Apple
  # Silicon runs fusion-mlx natively. Uncomment + set FUSION_MLX_URL above to
  # http://fusion-mlx:11432/v1 to use this service instead of host.
  # fusion-mlx:
  #   image: ghcr.io/dahai80/fusion-mlx:latest
  #   container_name: fusion-mlx
  #   ports:
  #     - "11432:11432"
  #   volumes:
  #     - mlx-models:/root/.cache/huggingface
  #   restart: unless-stopped

volumes:
  fusion-bench-data:
  fusion-bench-tasks:
  # mlx-models:
```

- [ ] **Step 2: Create `scripts/docker_smoke.sh`**

```bash
#!/usr/bin/env bash
# Docker smoke test for fusion-bench — build image + run --help (exit 0).
# CI verification, not pytest. Usage: ./scripts/docker_smoke.sh

set -euo pipefail

IMAGE="fusion-bench:smoke"

echo "[smoke] Building image ${IMAGE}..."
docker build -t "${IMAGE}" .

echo "[smoke] Running fusion-bench --help..."
docker run --rm "${IMAGE}" fusion-bench --help

echo "[smoke] PASS: image builds and CLI starts."
```

Then make it executable:

```bash
chmod +x scripts/docker_smoke.sh
```

- [ ] **Step 3: Run the smoke test**

Run: `./scripts/docker_smoke.sh`
Expected: PASS — image builds, `fusion-bench --help` exits 0, prints "PASS".

If Docker is unavailable in the environment, document this as a manual CI step (the script is the verification artifact). Note in the commit message if skipped.

- [ ] **Step 4: Commit Tasks 13 + 14 together**

```bash
git add Dockerfile docker-compose.yml scripts/docker_smoke.sh
git commit -m "fix(docker): python:3.12 base, port 11450, non-root user, drop NVIDIA GPU block"
```

## Final Verification

**Files:**
- All Release 1 files

- [ ] **Step 1: Full test suite green**

Run:
```bash
source .venv/bin/activate
pytest tests/ -q
```
Expected: PASS — all existing + new tests green. Includes `test_auth.py` (extended), `test_cache_integration.py` (new), `test_judge.py` (new), `test_cli_judge.py` (new), `test_cli_cache.py` (Task 7).

- [ ] **Step 2: CLI smoke (no model)**

Run:
```bash
fusion-bench --help
fusion-bench cache stats
fusion-bench judge create --name smoke --model qwen --type hybrid
fusion-bench judge list
fusion-bench judge show --name smoke
fusion-bench judge delete --name smoke
```
Expected: each exits 0, no tracebacks. (Auth CLI verified in Task 4; run flags in Task 7.)

- [ ] **Step 3: Lint (project has ruff)**

Run: `ruff check .`
Expected: PASS — no new violations in touched files. Fix any introduced by new modules.

- [ ] **Step 4: Import sanity**

Run:
```bash
python -c "import fusion_bench.judge; import fusion_bench.storage.judge_store; import fusion_bench.auth.identity; print('ok')"
```
Expected: prints `ok` (all new modules import cleanly).

- [ ] **Step 5: Docker smoke (if Docker available)**

Run: `./scripts/docker_smoke.sh`
Expected: PASS.

- [ ] **Step 6: Final commit (docs only, if any README updates needed)**

Per repo rule (update README when code changes warrant), check `README.md` for new CLI commands (`api-key`, `cache`, `judge`). If the README documents CLI usage, add the new subcommands. If not, skip — no speculative doc additions.

```bash
# Only if README needs updates:
git add README.md
git commit -m "docs: Release 1 — api-key/cache/judge CLI commands"
```

Release 1 complete. R2 (multi-tenant/distributed/scheduler), R3 (PB storage/HA), R4 (K8s/sandbox/ecosystem) deferred to future cycles per spec out-of-scope section.
