# Plan: integrate fusion-identity (issue #16)

## Goal
Retire local api-key/OAuth/RBAC re-implementation; consume fusion-identity
as sole JWT issuer + tenant registry. Enforce tenant context (fail-closed,
cross-tenant denied, data isolation). Report benchmark token usage centrally.

## Upstream contracts (read-only, verified)
- `POST http://127.0.0.1:11470/api/v1/auth/verify` body `{token}`, header
  `Authorization: Bearer <FUSION_IDENTITY_SERVICE_TOKEN>` →
  `{tid, role, scopes, quota, tenant_status, revoked}`. 401 on invalid.
- `POST /api/v1/tenants/{tid}/usage` body `UsageEmit{metric, value, source, model?, user_id?}`,
  same service-token header → `{metric, value}`.
- `fusion_core.tenant.install_tenant_middleware(app, *, exempt_paths=None,
  verify_jwt=Callable[[str], dict], require_jwt=True)`. Middleware: missing
  X-Tenant-Id → 401; jwt.tid ↔ header mismatch → 401; sets TenantContext
  (tenant_id, user_id, role, jti, scopes) via contextvar.
- Identity unified roles: `tenant_admin, operator, member, viewer`.

## Tasks

### T1 deps
- pyproject.toml: add `fusion-core`, `fusion-identity` to dependencies.

### T2 auth/tenant.py (new)
- `_verify_jwt(token) -> dict`: sync httpx.post to identity /auth/verify.
  Service token from `FUSION_IDENTITY_SERVICE_TOKEN` env (fail-closed if
  unset → raise). Identity URL from `FUSION_IDENTITY_URL` (default
  http://127.0.0.1:11470). On non-200 or tenant_status != active → raise.
  Return `{"tid":..., "role":<mapped bench role>, "scopes":[...]}`.
- `_map_role(identity_role) -> str`: tenant_admin→admin, operator→operator,
  member→operator, viewer→viewer, else viewer.
- `_report_usage(tenant_id, metric, value, model, user_id)`: POST
  /api/v1/tenants/{tid}/usage; best-effort (log warning on failure, never
  block benchmark).

### T3 auth/rbac.py refactor
- Keep `Permission` enum + `ROLE_PERMISSIONS` (keyed by bench role str).
- Remove `RBACStore`, `Role` enum, `has_permission` store fn (or keep Role
  as pure str alias for back-compat in CLI mapping).
- `require_permission(permission)`: read `TenantContext.current()`; if None
  → 401 (fail-closed, no anonymous, no default-tenant). If role not in
  ROLE_PERMISSIONS → 403.

### T4 app.py
- Replace `IdentityMiddleware` import+install with
  `install_tenant_middleware(app, verify_jwt=_verify_jwt,
  exempt_paths={health, openapi, docs, redoc})`.
- Keep TLS middleware.

### T5 trace_store tenant_id
- Add `tenant_id TEXT NOT NULL DEFAULT ''` column + migration
  (PRAGMA table_info check). Index idx_traces_tenant.
- `insert(record, tenant_id)`; `query(..., tenant_id)` filter; stats scoped
  by tenant. TraceRecord gains `tenant_id` field.
- app.py trace insert reads `TenantContext.current().tenant_id`.

### T6 usage reporting
- After benchmark result saved, call `_report_usage(tenant_id, "tokens",
  <token_count>, model, user_id)`. Best-effort, fire-and-log.

### T7 CLI api-key retire
- `cmd_api_key`: replace body with message "API keys now issued by
  fusion-identity (POST /api/v1/tenants/{tid}/api-keys)". Keep subcommand
  so old scripts don't crash but print guidance.

### T8 tests rewrite
- test_auth.py: remove RBACStore/OAuthResolver/IdentityMiddleware tests;
  add tenant-middleware tests with mocked `_verify_jwt`: valid token +
  matching X-Tenant-Id → 200; missing X-Tenant-Id → 401; tid mismatch →
  401; role permission enforced; exempt path passes.
- test_api_r1.py: replace api-key fixtures with tenant fixtures
  (monkeypatch _verify_jwt to return role dict; set X-Tenant-Id header).
  Cross-tenant trace access denied. Update judges/datasets tests to send
  X-Tenant-Id + Bearer.

## Acceptance (from issue)
- [ ] fusion-identity + fusion-core in pyproject.toml
- [ ] verify_jwt calls /auth/verify; missing/invalid → 401 fail-closed
- [ ] X-Tenant-Id required on non-exempt; tid ↔ header match enforced
- [ ] require_permission reads TenantContext.role (registry-backed)
- [ ] no default-tenant degradation — missing tid → 401
- [ ] local api_keys/user_roles retired
- [ ] benchmark token usage reported to /usage
- [ ] tests: cross-tenant denied; missing X-Tenant-Id → 401; tenant A
      cannot read tenant B traces

## Verify
- ruff check + ruff format --check clean
- pytest tests/ --ignore=tests/test_judge_e2e.py green
- CI green
