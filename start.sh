#!/bin/bash
# Fusion-Bench — Start/Stop script
# Usage: ./start.sh [start|stop|restart|status|bench]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Config
MLX_URL=${FUSION_MLX_URL:-"http://localhost:11434/v1"}
PID_FILE="$SCRIPT_DIR/.fusion-bench.pid"
LOG_DIR="$SCRIPT_DIR/logs"
STDOUT_LOG="$LOG_DIR/stdout.log"
STDERR_LOG="$LOG_DIR/stderr.log"

ensure_log_dir() {
    mkdir -p "$LOG_DIR"
}

get_pid() {
    if [ -f "$PID_FILE" ]; then
        cat "$PID_FILE"
    else
        echo ""
    fi
}

is_running() {
    local pid=$(get_pid)
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
        return 0
    fi
    return 1
}

start() {
    if is_running; then
        echo "Fusion-Bench is already running (PID $(get_pid))"
        exit 1
    fi
    ensure_log_dir
    echo "Starting Fusion-Bench ..."
    echo "  MLX URL: $MLX_URL"
    nohup python3 -m fusion_bench.api.server \
        --mlx-url "$MLX_URL" \
        >> "$STDOUT_LOG" 2>> "$STDERR_LOG" &
    PID=$!
    echo $PID > "$PID_FILE"
    echo "Started (PID $PID)"
}

stop() {
    local pid=$(get_pid)
    if [ -z "$pid" ]; then
        echo "Fusion-Bench is not running"
        return
    fi
    echo "Stopping Fusion-Bench (PID $pid) ..."
    kill "$pid" 2>/dev/null || true
    rm -f "$PID_FILE"
    for i in {1..5}; do
        if ! kill -0 "$pid" 2>/dev/null; then
            echo "Stopped"
            return
        fi
        sleep 1
    done
    kill -9 "$pid" 2>/dev/null || true
    echo "Stopped (forced)"
}

restart() {
    stop; sleep 1; start
}

status() {
    if is_running; then
        echo "Fusion-Bench is running (PID $(get_pid))"
    else
        echo "Fusion-Bench is not running"
    fi
}

bench() {
    MODEL="${1:-qwen3.5-9b}"
    echo "Running benchmark for model: $MODEL"
    echo "  MLX URL: $MLX_URL"
    echo ""
    python3 -c "
import asyncio, json
from fusion_bench.engine.benchmark import BenchmarkRunner

async def run():
    runner = BenchmarkRunner(mlx_base_url='$MLX_URL')
    results = await runner.benchmark('$MODEL', runs=2)
    for r in results:
        print(json.dumps(r.metrics.to_dict(), indent=2))
    await runner.close()

asyncio.run(run())
"
}

case "${1:-status}" in
    start) start ;;
    stop) stop ;;
    restart) restart ;;
    status) status ;;
    bench) bench "$2" ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|bench [model]}"
        echo ""
        echo "Environment:"
        echo "  FUSION_MLX_URL    fusion-mlx URL (default: http://localhost:11434/v1)"
        exit 1
        ;;
esac