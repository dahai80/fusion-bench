#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# deploy.sh — Build & deploy bench-site to production server
# Usage:  ./deploy.sh [--skip-build] [--skip-restart]
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

SSH_KEY="${SSH_KEY:-$HOME/.ssh/bench_server_key}"
SSH_HOST="${SSH_HOST:-root@47.82.117.121}"
REMOTE_DIR="${REMOTE_DIR:-/opt/bench-site/.next/standalone}"
SERVICE_NAME="${SERVICE_NAME:-bench-site}"

# ---- colours ----
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; }

# ---- pre-flight checks ----
for cmd in rsync ssh; do
    if ! command -v "$cmd" &>/dev/null; then
        error "Missing required command: $cmd"
        exit 1
    fi
done

if [[ ! -f "$SSH_KEY" ]]; then
    error "SSH key not found: $SSH_KEY"
    echo "  Set SSH_KEY env var or create the key at: $SSH_KEY"
    exit 1
fi

SSH_CMD="ssh -i $SSH_KEY -o StrictHostKeyChecking=no -o ConnectTimeout=10"

# ---- 1. Build ----
SKIP_BUILD=${SKIP_BUILD:-false}
if [[ "${1:-}" == "--skip-build" ]]; then
    SKIP_BUILD=true
fi

if ! $SKIP_BUILD; then
    info "Building production bundle (standalone)..."
    npm run build
    info "Build completed successfully."
else
    warn "Skipping build (--skip-build)."
fi

# ---- 2. Rsync to server ----
info "Syncing standalone build to ${SSH_HOST}:${REMOTE_DIR} ..."
rsync -avz --delete \
    --exclude='data/' \
    --exclude='node_modules/' \
    -e "ssh -i $SSH_KEY -o StrictHostKeyChecking=no" \
    .next/standalone/ \
    "${SSH_HOST}:${REMOTE_DIR}/"
info "Sync completed."

# ---- 3. Restart service ----
SKIP_RESTART=${SKIP_RESTART:-false}
if [[ "${1:-}" == "--skip-restart" ]]; then
    SKIP_RESTART=true
fi

if ! $SKIP_RESTART; then
    info "Restarting ${SERVICE_NAME} service..."
    $SSH_CMD "$SSH_HOST" "systemctl daemon-reload && systemctl restart $SERVICE_NAME"

    # Wait for service to come up
    sleep 3

    # Health check
    STATUS=$($SSH_CMD "$SSH_HOST" "systemctl is-active $SERVICE_NAME" 2>/dev/null || echo "unknown")
    if [[ "$STATUS" == "active" ]]; then
        info "Service ${SERVICE_NAME} is active."

        # Quick HTTP check via nginx (port 80)
        HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 http://47.82.117.121/ 2>/dev/null || echo "000")
        if [[ "$HTTP_CODE" == "200" ]]; then
            info "Deployment verified — site returns HTTP 200."
        else
            warn "Service is running but HTTP check returned $HTTP_CODE (nginx may not be configured)."
        fi
    else
        error "Service ${SERVICE_NAME} is NOT active (status=$STATUS)."
        $SSH_CMD "$SSH_HOST" "journalctl -u $SERVICE_NAME --no-pager -n 30" || true
        exit 1
    fi
else
    warn "Skipping restart (--skip-restart)."
fi

echo ""
info "Deploy finished successfully!"