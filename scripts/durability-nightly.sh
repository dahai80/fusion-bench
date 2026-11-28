#!/usr/bin/env bash
# Local nightly durability refresh (issue #70): regenerate the report from
# live supervisor/cowork records on the data-owner machine, refresh the
# committed dataset, and run the same verify gate CI runs. Run via cron or
# fusion-sv schedule; commit refreshed artifacts only when verify passes.
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${PYTHON:-python}"

"$PY" -m fusion_bench.cli durability report --out bench/durability
"$PY" -m fusion_bench.cli durability dataset --out bench/durability/dataset-v1.json
"$PY" -m fusion_bench.cli durability verify \
    --dataset bench/durability/dataset-v1.json \
    --report bench/durability/durability-report.json
echo "durability nightly: verify passed"
if [ "${COMMIT:-0}" = "1" ]; then
    git add bench/durability/
    if ! git diff --cached --quiet; then
        git commit -m "chore(durability): nightly report refresh"
        git push origin main
    fi
fi
