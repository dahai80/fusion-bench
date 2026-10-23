# Fusion-Bench Web 控制台

fusion-bench 的 Web UI 包 (issue #23, PRD N-5)。三个页面, 数据来自 REST API
`127.0.0.1:11467`:

- **Tasks** — 提交表单 (model / executor / level / suite) + 任务表 (5s 轮询);
  点选任务看实时详情 TaskProgress (选中时 2s 轮询); cancel / retry 走危险确认
  弹窗 (spec S5)。
- **Results** — `/api/v1/results/trend` 指标趋势图 + 最新/均值/模型数 tiles
  (15s 轮询)。
- **Compare** — 选 2+ 个已完成任务, `POST /api/v1/results/compare`, 指标对比表
  (value / pass rate / cases)。

## 鉴权

API 经 fusion-identity JWT fail-closed (issue #16): 每个请求需 `X-Tenant-Id` +
`Authorization: Bearer`。**UI 不带任何鉴权逻辑** — 嵌入模式由 shell 会话经网关
`/shell/fusion-bench/` 代理注入两头部; 独立 dev 从 `VITE_BENCH_TENANT` /
`VITE_BENCH_TOKEN` 接线 (仅 dev 便利)。

## 技术栈

React 18 + Vite 5 + TypeScript + Tailwind (fusion preset) + Bun, 复用
`@fusion/web-ui` 组件 (StatusBadge/TaskProgress/MetricChart/MetricTile/
DataTable/ConfirmDialog) 与 `@fusion/web-sdk`, 通过 `file:vendor/@fusion`
引入 — 零 registry 依赖。

## 开发

```bash
cd web
bun install
bun run dev        # vite 11474, 代理 /api /health /ready → 11467
bun run build      # typecheck + vite build → dist/
bun run lint       # biome
```

`FUSION_DEV_BACKEND` 覆盖后端地址 (默认 `http://127.0.0.1:11467`)。
`FUSION_BENCH_WEB_PORT` 覆盖 dev 端口。

## 网关接线 (嵌入模式)

`/shell/fusion-bench/` 代理是网关静态配置:

```toml
[web_shell.modules.fusion-bench]
upstream = "http://127.0.0.1:11467"
```

shell 注册 manifest 见 `web/manifest.json` (category `platform`, devices
desktop + mobile-readonly, `api_key_env` = `FUSION_BENCH_TOKEN`)。
