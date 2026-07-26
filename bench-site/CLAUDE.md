# Bench-Site CLAUDE.md

Bench-site is the web UI component of Fusion-Bench, deployed at [bench.dpdns.org](https://bench.dpdns.org).

## Architecture

- **Framework:** Next.js 16.2.9 (App Router) with standalone output
- **Database:** better-sqlite3 + drizzle-orm (SQLite at `data/bench.db`)
- **Styling:** Tailwind CSS 4
- **Charts:** recharts

## Database Schema

Source of truth: `src/db/schema.ts`. The `benchmarks` table has 4 indexes:
- `idx_bench_model` on (model_name, quantization)
- `idx_bench_chip` on (chip_name, memory_gb)
- `idx_bench_owner` on (owner_hash)
- `idx_bench_created` on (created_at)

**Important:** If the schema changes, fusion-bench's `reporter/bench_site_db.py._ensure_schema()` must also be updated.

## API Routes

| Route | Method | Description |
|-------|--------|-------------|
| `/api/benchmarks` | POST | Submit benchmark (dedup by owner+chip+model+quant+ctx) |
| `/api/benchmarks` | GET | Query with filtering, sorting, pagination |
| `/api/benchmarks/[id]` | GET | Single benchmark by ID |
| `/api/benchmarks/aggregate` | GET | Group by chip/model/quant with avg/max/min |
| `/api/benchmarks/stats` | GET | Total submissions/chips/models + latest 10 |

## Development

```bash
npm install
npm run dev          # http://localhost:3000
```

## Build & Deploy

```bash
npm run build        # Standalone output in .next/standalone/
./deploy.sh          # Build + rsync to 47.82.117.121 + systemctl restart
./deploy.sh --skip-build    # Deploy without rebuilding
```

Production runs as systemd service `bench-site` on the remote server.

## Pages

- `/` — Homepage with stats and latest submissions
- `/benchmarks` — Browse/filter/sort all submissions
- `/benchmarks/[id]` — Single benchmark detail
- `/performance` — Performance comparison charts
- `/get-started` — Guide for new users
- `/my/[hash]` — User's submissions by owner_hash
