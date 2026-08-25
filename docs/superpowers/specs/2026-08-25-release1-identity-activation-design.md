# Release 1 — Identity & Activation (Design Spec)

**Date:** 2026-08-25
**Status:** Draft
**Scope:** fusion-bench enterprise release, Release 1 of 4 (R1 identity base → R2 multi-tenant/distributed → R3 storage/HA → R4 K8s/sandbox/ecosystem).
**Baseline:** v0.3.7. Source of deferred items: `architecture/bench.md` §16 (tech-debt & gap analysis). Verified against current code 2026-08-25.

## Purpose

Close §16 deferred items blocking enterprise production: authentication layer, cache integration, LLM-as-Judge, and broken Docker (K8s prerequisite). Establish identity foundation that Release 2 multi-tenancy builds on.

## Deferred Items Addressed

| §16 ref | Item | Status (verified 2026-08-25) | Release 1 action |
|---------|------|------------------------------|------------------|
| §16.2 #1 | Auth missing — RBAC has model but identity hardcoded `anonymous` | Deferred | Real auth layer (API Key + OAuth2) |
| §16.2 #3 | SchedulerEngine inactive | Deferred | **Out of R1** — R2 |
| §16.2 #4 | LLM-as-Judge not integrated | Deferred | Judge module + Agent/Artifact integration |
| §16.2 #6 | Cache not integrated | Deferred | Pipeline cache integration |
| §16.2 #5 | SSE not emitted | **Fixed** (pipeline.py:323/438/501) | No action |
| — | Docker broken (3.11 base, wrong port, NVIDIA GPU on Apple Silicon) | Broken | Dockerfile + compose fix |

SSE confirmed already fixed — removed from scope. Scheduler/Distributed deferred to R2 (dependency on R1 identity for multi-tenant scheduling).

## Section 1 — AUTH

**Problem:** `require_permission` (auth/rbac.py:140) hardcodes `user_id="anonymous"`. Every endpoint passes permission check because RBAC returns VIEWER for unknown users — no real authentication. Release 2 multi-tenancy needs real identity.

### Architecture

```
Request → IdentityMiddleware (new)
            ├─ header X-API-Key → ApiKeyResolver → api_keys table
            ├─ header Authorization: Bearer <jwt> → OAuthResolver → IdP JWKS verify
            └─ none → anonymous (VIEWER, read-only endpoints only)
          → request.state.identity = Identity(user_id, workspace_id, role, source)
          → require_permission reads identity from request.state, not "anonymous"
```

### New module: `fusion_bench/auth/identity.py`

- `Identity` dataclass: `user_id: str`, `workspace_id: str` (R2 use; R1 stores), `role: Role`, `source: str` ("apikey"|"oauth"|"anonymous"), `scopes: list[str]`.
- `IdentityMiddleware(BaseRequestMiddleware)`: runs resolvers in order, attaches `request.state.identity`. Short-circuits on first success.
- `ApiKeyResolver`: query `api_keys` table (created in `RBACStore._ensure_table`). Constant-time lookup, record `last_used`, reject `revoked=1`. Returns `Identity(user_id, workspace_id, role, source="apikey")`.
- `OAuthResolver`: fetch JWKS via httpx (cached, refresh on kid miss), verify JWT signature + exp + aud (`FUSION_BENCH_OAUTH_AUDIENCE`), extract `sub` + role claim. claim→Role mapping: claim value matches Role enum string. Returns `Identity(sub, workspace_id from claim, role, source="oauth")`.
- `require_permission(permission, allow_anonymous=False)` (refactor rbac.py:137): resolve `Request` from kwargs, read `request.state.identity`, check `identity.role` against `ROLE_PERMISSIONS`. `allow_anonymous=True` for public read-only endpoints (GET /tasks, /gates).

### RBAC extension (`auth/rbac.py`)

- `user_roles` table: add `workspace_id TEXT DEFAULT 'default'` column (ALTER TABLE IF NOT EXISTS pattern). Indexed in R2.
- New `api_keys` table: `api_key TEXT PK, user_id TEXT, workspace_id TEXT, role TEXT, scopes TEXT, created_at TEXT, last_used REAL, revoked INTEGER DEFAULT 0`. Key = `secrets.token_urlsafe(32)`.
- New admin methods on `RBACStore`: `create_api_key(user_id, role, workspace_id="default", scopes=[]) -> str`, `revoke_api_key(api_key) -> bool`, `list_api_keys()`, `verify_api_key(api_key) -> Identity | None`.
- New Permission values: none — existing 10 cover endpoints.
- Bootstrap: first startup with empty `api_keys` + `FUSION_BENCH_BOOTSTRAP_ADMIN=1`, auto-generate root key, print to stdout once (fusion-mlx key bootstrap pattern). Persist.

### Config (env, no secrets in code — repo rule)

- `FUSION_BENCH_API_KEY_ENABLED=1` (default on)
- `FUSION_BENCH_OAUTH_ENABLED=0` (default off; enable when IdP configured)
- `FUSION_BENCH_OAUTH_JWKS_URL` (e.g. Authentik `…/application/o/fusion-bench/jwks/`)
- `FUSION_BENCH_OAUTH_ISSUER`, `FUSION_BENCH_OAUTH_AUDIENCE`
- `FUSION_BENCH_OAUTH_ROLE_CLAIM="roles"`
- `FUSION_BENCH_BOOTSTRAP_ADMIN=0`
- `FUSION_BENCH_AUTH_STRICT=0` (when 1: deny anonymous on write endpoints; when 0: allow + log warning during transition)

### CLI

`fusion-bench api-key create --user <id> --role <role> [--workspace <id>] [--scopes ...]` → prints key once.
`fusion-bench api-key revoke <key>` / `list`.

### Tests (`tests/test_auth.py` extended)

- API Key: issue/verify/revoke, revoked key rejected, last_used updated.
- OAuth: JWKS verify with mocked JWKS server (httpx mock), expired token rejected, wrong audience rejected, role claim mapping.
- Middleware: resolver order (API Key wins if both headers), anonymous fallback.
- Anonymous: denied on write endpoint when `AUTH_STRICT=1`, allowed (VIEWER) when 0.
- pytest-mock; no real IdP call.

### Files touched

`auth/rbac.py` (refactor `require_permission` + `api_keys` table + admin methods), `auth/identity.py` (new), `api/app.py` (add middleware + update `require_permission(…, allow_anonymous=…)` on protected endpoints), `cli.py` (`api-key` subcommand), `tests/test_auth.py`.

### Backward compatibility

Anonymous stays VIEWER (read-only) — local/CLI users unaffected. Write endpoints accept anonymous until `FUSION_BENCH_AUTH_STRICT=1` (transition window, log warning).

## Section 2 — CACHE

**Problem:** `BenchmarkCache` (cache.py) fully implemented (`get`/`set`/`clear`/`stats`), never called. Same model+config+task re-runs every suite.

### Integration point

Pipeline `_run_one_with_retry` (pipeline.py:361-399). After `TaskConfig` built (~line 378), before circuit-breaker check — query cache. After executor returns success — write cache.

### Determinism gate

Cache hit only when ALL hold:
- `temperature == 0` (or unset → default 0)
- `random_seed` fixed (TaskConfig default 42 = deterministic)
- `max_samples` set (not None — None = full dataset, ambiguous count, skip)

Non-deterministic → skip cache, log `cache_miss:non_deterministic`. Helper `_is_deterministic(config) -> bool` + `_cache_key(config) -> dict` extracting temperature/seed/max_samples from `config.params` with known key aliases (`temperature`/`temp`/`temp` in scenario configs).

### Cache key extension

Current key: `model + config_json + task`. Add `executor_key` — same task_id under different executor = different result. Change `BenchmarkCache.get/set` signature to `(model, config, task, executor_key)`. Schema migration: `ALTER TABLE benchmarks ADD COLUMN executor_key TEXT NOT NULL DEFAULT 'speed'` + extend index. Backfill existing rows default "speed".

### Pipeline changes (`orchestrator/pipeline.py`)

- Constructor: accept `cache: BenchmarkCache | None = None`, `use_cache: bool = True`. Inject (testable, not constructed inside).
- `_run_one_with_retry`:
  ```
  if self.use_cache and self.cache and _is_deterministic(config):
      cached = self.cache.get(model, config.params, task_id, executor_key)
      if cached:
          stream.emit(suite_id, "cache_hit", {"task_id": task_id})
          return EvalResult(**cached)  # skip executor
  ...executor runs...
  if success and self.cache and _is_deterministic(config):
      self.cache.set(model, config.params, task_id, executor_key, result.to_dict())
  ```
- Cache hit/miss emit via existing `stream.emit` (SSE already wired).
- **Trace policy:** cache hit → skip `_record_trace` (original run already traced; re-tracing distorts TraceStore trends with new timestamps). Record lightweight audit row `source=cache` via AuditStore (mature). Keeps trends honest.

### Concurrency

Semaphore gates executor calls. Cache reads/writes SQLite own connection. Add `PRAGMA journal_mode=WAL` to cache `_init_db` (currently absent — fix). Concurrent `set` same key = `INSERT OR REPLACE` (already safe).

### TTL / invalidation

Add optional `ttl_seconds` (default None = forever). On `get`: `created_at + ttl < now` → treat as miss + delete stale row. Model retrain invalidates manually via existing `clear(model=...)`.

### CLI

`fusion-bench run --no-cache` / `--cache-ttl 3600`. `fusion-bench cache stats|clear [--model X]` subcommand (BenchmarkCache.stats/clear already exist — wire CLI).

### Tests (`tests/test_cache_integration.py` new)

- Deterministic config hits cache (second run skips executor; mock executor call count = 1).
- Non-deterministic misses (call count = 2).
- executor_key isolation (same task, different executor = 2 runs).
- TTL expiry (set ttl=1s, sleep, miss).
- Cache hit emits SSE, no trace record.
- Concurrent writes safe (2 tasks same key).

### Files touched

`cache.py` (signature + WAL + TTL), `orchestrator/pipeline.py` (inject + query/write + determinism helper + emit), `cli.py` (`--no-cache`, `--cache-ttl`, `cache` subcommand), `tests/test_cache_integration.py` (new).

### Backward compatibility

`use_cache` default True but cache empty first run = no behavior change. Signature change internal (no external callers).

## Section 3 — JUDGE (LLM-as-Judge)

**Problem:** Agent `TrajectoryScorer` (rule-based: tool-correctness + self-correction) and Artifact `criteria_eval` (rule-based format check) only. No LLM-judge. Subjective quality (answer correctness, reasoning, helpfulness) unmeasured. Per §16.2 #4.

### New module: `fusion_bench/judge/`

- `judge/base.py` — `Judge` ABC: `async judge(judge_input: JudgeInput) -> JudgeVerdict`.
  - `JudgeInput(prompt: str, expected: str|None, actual: str, criteria: list[str], rubric: str = "")`
  - `JudgeVerdict(score: float 0-1, reasoning: str, per_criterion: dict[str,float])`
- `judge/llm_judge.py` — `LLMJudge(Judge)`: calls fusion-mlx `/chat/completions` (same HTTP API, no new deps — reuses httpx client pattern from engine/benchmark.py). Prompt template forces JSON `{score, reasoning}` → parse via `_parse_json()`-style helper (fusion-core pattern). Strict: parse failure → score 0.5 neutral + log, never crash suite.
- `judge/config.py` — `JudgeConfig` dataclass: `judge_model: str` (default same as eval model), `judge_type: "llm"|"rule"|"hybrid"`, `weight: float` (judge weight, default 0.5), `criteria: list[str]`, `rubric: str`, `temperature: float = 0` (judge deterministic). Stored in `storage/judge_store.py` (`JudgeStore` SQLite, keyed by name) — fixes "JudgeConfig stored but not integrated".
- `judge/__init__.py` — `get_judge(config: JudgeConfig) -> Judge` factory.

### Integration — Agent (agent_executor.py:339)

Current: `combined_score = 0.5 * criteria_eval["score"] + 0.5 * traj["trajectory_score"]`
New: if `task_config.params.get("judge")` names a JudgeConfig:
```
rule_score = 0.5*criteria_eval["score"] + 0.5*traj["trajectory_score"]
if judge_config:
    verdict = await judge.judge(JudgeInput(scenario.task, scenario.expected, final_answer, judge_config.criteria, judge_config.rubric))
    if judge_type == "hybrid": final = weight*verdict.score + (1-weight)*rule_score
    elif judge_type == "llm":  final = verdict.score
    else: final = rule_score  # "rule"
else:
    final = rule_score
passed = final >= threshold
```

### Integration — Artifact (artifact_executor.py:179)

Current: `eval_result["score"]` from rule format check.
New: `_evaluate_case` post-rule, if judge config present, call `judge.judge` with artifact text + criteria, blend per `weight`. Same hybrid/llm/rule switch.

### TaskConfig plumbing

`params["judge"] = "<judge_name>"` (string ref to JudgeStore). Resolve inside executor via `JudgeStore.get(name)`. Keeps TaskConfig flat — no new required field, backward compatible (no judge key = current rule behavior).

### Determinism + cost

Judge adds 1 LLM call per case. `max_samples` bounds cost. Judge `temperature=0` enforced. Judge results folded into EvalResult → cached via Section 2 (no separate judge cache — reuse, don't duplicate).

### Failure handling

Judge LLM call fails/timeout → fall back to `rule_score`, log `judge_fallback`, set `meta["judge_source"]="fallback"`. Never fail suite on judge error. Timeout = `task_config.timeout_seconds`.

### CLI

`fusion-bench judge create --name X --model Y --type hybrid --weight 0.5 --criteria ...` / `list` / `show`. `fusion-bench run --judge <name>` or suite task params carry judge name.

### Tests (`tests/test_judge.py` new)

- LLMJudge JSON parse (valid/malformed/timeout → fallback).
- Hybrid weighting math (assert blend correct).
- Agent integration: mock judge returns fixed verdict, assert `combined_score` blend.
- Artifact integration: same.
- Rule-only (`judge_type="rule"`): unchanged score.
- JudgeStore CRUD (create/get/list/delete).

### Files touched

`judge/base.py`, `judge/llm_judge.py`, `judge/config.py`, `judge/__init__.py` (new dir), `storage/judge_store.py` (new), `executors/agent_executor.py` (score blend), `executors/artifact_executor.py` (score blend), `cli.py` (`judge` subcommand), `tests/test_judge.py` (new).

### Backward compatibility

No `judge` param = pure rule scoring, zero behavior change. Existing tests unaffected.

## Section 4 — DOCKER Fix

**Problem:** Dockerfile + docker-compose broken — blocks Release 4 K8s. Three concrete defects:

1. **Wrong base image:** `python:3.11-slim`, but pyproject requires `>=3.12`. `enum.StrEnum` (used in rbac.py:14) is 3.11+ but other 3.12 syntax may break under 3.11 runtime. Must be `python:3.12-slim`.
2. **Wrong port:** `EXPOSE 8000` + healthcheck `localhost:8000`, but `fusion-bench serve` default is **11450** (cli.py:131). Healthcheck always fails → orchestrator marks unhealthy.
3. **Wrong GPU driver:** docker-compose requests **NVIDIA** GPU (`driver: nvidia`). fusion-mlx is Apple Silicon MLX — no NVIDIA GPU. Block fails on Apple Silicon host.

### Dockerfile fix

- `FROM python:3.12-slim` (align pyproject + repo `.python-version` 3.12).
- `EXPOSE 11450`.
- Healthcheck: `CMD curl -f http://localhost:11450/health || exit 1`.
- Non-root `USER`: create `fusion` user, chown /app, run as `fusion` (production safety — root container flagged).
- Keep: apt install git/curl/build-essential, `pip install --no-cache-dir -e ".[test]"`, VOLUME paths. Single-stage (multi-stage = overkill, keep simple).

### docker-compose.yml fix

- fusion-bench service: port 11450 already correct in mapping. Rely on Dockerfile HEALTHCHECK. Add `FUSION_BENCH_OAUTH_JWKS_URL` etc. as commented placeholders (post-R1 AUTH config).
- **fusion-mlx service:** remove `deploy.resources.reservations.devices` NVIDIA block. MLX runs on host Metal — no GPU passthrough in Apple Silicon containers.
  - Decision: mark fusion-mlx service **optional** — comment out + document "run fusion-mlx natively on Apple Silicon host, set `FUSION_MLX_URL=http://host.docker.internal:11432/v1`". Keep service available for non-Apple CI with CPU image, NVIDIA block removed.
- Add `FUSION_MLX_URL` env pointing to host.docker.internal (macOS Docker Desktop).

### Verification

`scripts/docker_smoke.sh` (new): `docker build -t fusion-bench . && docker run --rm fusion-bench fusion-bench --help` (exit 0). CI verification, not pytest.

### Files touched

`Dockerfile`, `docker-compose.yml`, `scripts/docker_smoke.sh` (new).

### Backward compatibility

Breaking fix to already-broken config. No functional code change. compose `FUSION_MLX_URL` env unchanged.

## Cross-Cutting

- **Logging:** all new modules use `logging.getLogger(__name__)` per repo convention. Cache hit/miss, judge fallback, auth resolution logged at INFO/WARNING.
- **No docstrings** (repo rule). Inline comments only.
- **4-space indent multiples** (repo rule).
- **No secrets in code** (repo rule) — all auth config via env vars.

## Testing Summary

- `tests/test_auth.py` — extended (API Key, OAuth JWKS mock, middleware, anonymous deny)
- `tests/test_cache_integration.py` — new (deterministic hit, non-deterministic miss, TTL, concurrency)
- `tests/test_judge.py` — new (LLM parse, hybrid blend, fallback, Agent/Artifact integration, JudgeStore CRUD)
- `scripts/docker_smoke.sh` — new (build + run --help)
- Existing suite (`pytest tests/`) must remain green.

## Rollout / Backward Compatibility

- AUTH: anonymous stays VIEWER (read-only) — local/CLI users unaffected. Strict enforcement gated behind `FUSION_BENCH_AUTH_STRICT=1`.
- CACHE: `use_cache` default True but empty cache = no behavior change first run.
- JUDGE: no `judge` param = pure rule scoring, zero behavior change.
- DOCKER: breaking fix to already-broken config; no code change.

## Out of Scope (later releases)

- R2: multi-tenant (workspace isolation on R1 identity), Distributed (`RemoteDistributor` → Pipeline), Scheduler (APScheduler daemon).
- R3: PB/object storage (S3/MinIO backend abstraction), HA (replica/failover, scheduler leader election).
- R4: K8s (Helm chart + operator, depends R1 Docker + R3 HA), SandboxFusion (hardened sandbox for Agent/Code), ecosystem integration (webhooks + fusion-* + MLflow/W&B).
