# Bench-Site

Public web UI for [Fusion-Bench](https://github.com/dahai80/fusion-mlx) — Apple Silicon LLM benchmarking platform. Live at [bench.dpdns.org](https://bench.dpdns.org).

## Features

- **5 Benchmark Types**: Speed, Accuracy, Security, Quant, Tune — all displayed with type-specific metrics and detail views
- **Performance Explorer**: Interactive charts with grouping by model, chip, quantization, type, or task
- **Community Submissions**: Browse, filter, and compare benchmarks across Apple Silicon hardware
- **API-Driven**: REST API for programmatic submission and querying

## Tech Stack

- Next.js 16 + React 19
- better-sqlite3 + drizzle-orm
- Tailwind CSS 4 + recharts

## Development

```bash
npm install
npm run dev
```

Open [http://localhost:11461](http://localhost:11461).

## Database Schema

The `benchmarks` table is defined in `src/db/schema.ts` (drizzle ORM). Key columns:

| Column | Type | Purpose |
|--------|------|---------|
| `benchmarkType` | text | speed / accuracy / security / quant / tune |
| `taskName` | text | Task identifier (e.g., mmlu, gsm8k) |
| `metricName` | text | Metric name (e.g., decode_speed, accuracy) |
| `metricValue` | real | Primary metric value |
| `detail` | text | Type-specific JSON detail |
| `tgTps` / `ppTps` | real | Speed metrics (0 for non-speed types) |
| `ttftMs` | real | Time to first token |

## API Endpoints

- `GET /api/benchmarks` — List/filter benchmarks (supports `benchmark_type`, `task_name` params)
- `POST /api/benchmarks` — Submit benchmark
- `GET /api/benchmarks/[id]` — Get single benchmark (parses detail JSON)
- `GET /api/benchmarks/aggregate` — Aggregate stats (supports `type`/`task` group_by, `metric_value` metric)
- `GET /api/benchmarks/stats` — Database statistics (includes `by_type` distribution)

## Deploy

```bash
./deploy.sh
```

Builds, rsyncs to server, and restarts the service.
