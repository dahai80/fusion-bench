# Fusion-Bench Web Console

Web UI package for fusion-bench (issue #23, PRD N-5). Three pages over the
REST API on `127.0.0.1:11467`:

- **Tasks** — submit form (model / executor / level / suite) + task table
  (5s poll); click a task for live detail with TaskProgress (2s poll while
  selected); cancel / retry behind a danger confirm dialog (spec S5).
- **Results** — metric trend chart from `/api/v1/results/trend` with
  latest/average/model tiles (15s poll).
- **Compare** — pick 2+ completed tasks, `POST /api/v1/results/compare`,
  metric table (value / pass rate / cases).

## Auth

The API is fail-closed behind fusion-identity JWTs (issue #16): every
request needs `X-Tenant-Id` + `Authorization: Bearer`. **The UI ships no
auth logic** — embedded mode the shell session injects both headers
upstream via the gateway `/shell/fusion-bench/` proxy; standalone dev wires
them from `VITE_BENCH_TENANT` / `VITE_BENCH_TOKEN` (dev convenience only).

## Stack

React 18 + Vite 5 + TypeScript + Tailwind (fusion preset) + Bun, sharing
`@fusion/web-ui` components (StatusBadge, TaskProgress, MetricChart,
MetricTile, DataTable, ConfirmDialog) and `@fusion/web-sdk` via
`file:vendor/@fusion` — zero registry dependencies.

## Dev

```bash
cd web
bun install
bun run dev        # vite on 11474, proxies /api /health /ready → 11467
bun run build      # typecheck + vite build → dist/
bun run lint       # biome
```

`FUSION_DEV_BACKEND` overrides the backend target (default
`http://127.0.0.1:11467`). `FUSION_BENCH_WEB_PORT` overrides the dev port.

## Gateway wiring (embedded mode)

The `/shell/fusion-bench/` proxy is static gateway configuration:

```toml
[web_shell.modules.fusion-bench]
upstream = "http://127.0.0.1:11467"
```

The shell registry manifest lives in `web/manifest.json` (category
`platform`, devices desktop + mobile-readonly, `api_key_env` =
 `FUSION_BENCH_TOKEN`).
