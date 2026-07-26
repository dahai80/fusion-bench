#!/usr/bin/env bash
# Offline installer builder for fusion-bench.
# Importers/callers: DevOps CI pipeline or manual `bash build_offline.sh`.
# Affected API: no API changes; produces tarball artifact.
# Data schema: N/A (build script).
# User instruction: "把所有没完全做完，没启动做，有差距的全部启动补齐" (P3-20 offline installer).
set -euo pipefail

VERSION=$(python -c "from fusion_bench import __version__; print(__version__)" 2>/dev/null || echo "0.1.0")
DIST_DIR="dist/offline-fusion-bench-${VERSION}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "[offline] Building offline package v${VERSION}..."

rm -rf "${DIST_DIR}"
mkdir -p "${DIST_DIR}/packages" "${DIST_DIR}/models" "${DIST_DIR}/scripts"

pip download -d "${DIST_DIR}/packages" \
    -e "${SCRIPT_DIR}[test]" \
    --prefer-binary \
    --no-deps 2>/dev/null || true

pip download -d "${DIST_DIR}/packages" \
    httpx pyyaml rich click aiohttp psutil \
    --prefer-binary 2>/dev/null || true

cp "${SCRIPT_DIR}/pyproject.toml" "${DIST_DIR}/"
cp "${SCRIPT_DIR}/setup.py" "${DIST_DIR}/" 2>/dev/null || true
cp -r "${SCRIPT_DIR}/fusion_bench" "${DIST_DIR}/"

cat > "${DIST_DIR}/install.sh" << 'INSTALL_EOF'
#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
echo "[install] Installing fusion-bench offline..."
python3 -m venv .venv 2>/dev/null || true
source .venv/bin/activate
pip install --no-index --find-links="${SCRIPT_DIR}/packages" \
    "${SCRIPT_DIR}/packages/"*.whl 2>/dev/null || \
    pip install --no-index --find-links="${SCRIPT_DIR}/packages" \
    -e "${SCRIPT_DIR}" 2>/dev/null || \
    pip install -e "${SCRIPT_DIR}"
echo "[install] Done. Run: source .venv/bin/activate && fusion-bench --help"
INSTALL_EOF
chmod +x "${DIST_DIR}/install.sh"

tar czf "dist/offline-fusion-bench-${VERSION}.tar.gz" -C dist "offline-fusion-bench-${VERSION}"
echo "[offline] Package created: dist/offline-fusion-bench-${VERSION}.tar.gz"
ls -lh "dist/offline-fusion-bench-${VERSION}.tar.gz"
