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
