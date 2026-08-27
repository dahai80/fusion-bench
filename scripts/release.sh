#!/usr/bin/env bash
# release.sh — cut a GitHub release aligned with the in-code version.
#
# Single source of truth: pyproject.toml `version`. This script ensures the
# Git tag and GitHub Release always match the version shipped in the code —
# run it after bumping the version (pyproject.toml + app.py OpenAPI + README
# changelog) and committing.
#
# Usage:
#   scripts/release.sh                 # tag + push + create GitHub release
#   scripts/release.sh --skip-tests    # skip the pre-release test/ruff gate
#
# Prerelease detection: a version containing rc/a/b/alpha/beta is published
# as a GitHub prerelease and never set as Latest; the highest stable tag
# becomes Latest automatically.
set -euo pipefail

# ── colours ─────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# ── preflight ──────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

command -v gh   >/dev/null 2>&1 || error "gh CLI not installed (https://cli.github.com)"
command -v git  >/dev/null 2>&1 || error "git not installed"
gh auth status >/dev/null 2>&1 || error "gh not authenticated (run: gh auth login)"

SKIP_TESTS=false
[[ "${1:-}" == "--skip-tests" ]] && SKIP_TESTS=true

# ── 1. read version from pyproject.toml (single source of truth) ────
VERSION="$(grep -m1 '^version' pyproject.toml | sed -E 's/version = "([^"]+)"/\1/')"
[[ -n "$VERSION" ]] || error "could not read version from pyproject.toml"
TAG="v${VERSION}"
info "In-code version: $VERSION  (tag: $TAG)"

# ── 2. sanity: tag must not already exist ───────────────────────────
if git rev-parse -q --verify "refs/tags/$TAG" >/dev/null; then
    error "tag $TAG already exists. Bump the version in pyproject.toml first."
fi

# ── 3. sanity: working tree clean (version bump must be committed) ─
if [[ -n "$(git status --porcelain --untracked-files=no | grep -vE '__pycache__|\.pyc$|egg-info|\.coverage')" ]]; then
    error "working tree has uncommitted changes (excluding build noise). Commit the version bump first."
fi

# ── 4. sanity: HEAD must be pushed to origin ───────────────────────
git fetch origin --quiet
LOCAL="$(git rev-parse HEAD)"
REMOTE="$(git rev-parse origin/main 2>/dev/null || git rev-parse origin/HEAD)"
[[ "$LOCAL" == "$REMOTE" ]] || error "HEAD not on origin. Run 'git push origin main' first."

# ── 5. pre-release gate: tests + ruff (unless --skip-tests) ────────
if ! $SKIP_TESTS; then
    info "Running ruff check..."
    ruff check fusion_bench/ tests/ >/dev/null
    info "Running pytest (excluding live e2e)..."
    pytest tests/ --ignore=tests/test_judge_e2e.py -q >/dev/null
    info "Pre-release gate passed."
else
    warn "Skipping pre-release test/ruff gate (--skip-tests)."
fi

# ── 6. create + push annotated tag ─────────────────────────────────
info "Creating tag $TAG at HEAD..."
git tag -a "$TAG" -m "Release $TAG"
git push origin "$TAG"
info "Tag $TAG pushed."

# ── 7. build release notes from README changelog ───────────────────
NOTES_FILE="$(mktemp)"
trap 'rm -f "$NOTES_FILE"' EXIT
python3 - "$VERSION" "$NOTES_FILE" <<'PYEOF'
import re, sys
version, out = sys.argv[1], sys.argv[2]
text = open("README.md", encoding="utf-8").read()
# Match the changelog heading for this version up to the next ### or EOF.
m = re.search(rf"(### v{re.escape(version)}[^\n]*\n)(.*?)(?=\n### |\Z)", text, re.DOTALL)
if not m:
    body = f"## v{version}"
else:
    body = (m.group(1) + m.group(2)).strip()
open(out, "w", encoding="utf-8").write(body + "\n")
PYEOF

# ── 8. create GitHub release (prerelease if rc/alpha/beta) ─────────
if echo "$VERSION" | grep -qiE "rc|alpha|beta|a[0-9]|b[0-9]"; then
    info "Version looks like a prerelease — creating GitHub prerelease."
    gh release create "$TAG" --title "$TAG" --prerelease --notes-file "$NOTES_FILE"
else
    info "Creating stable GitHub release and marking as Latest."
    gh release create "$TAG" --title "$TAG" --latest --notes-file "$NOTES_FILE"
fi

info "Done. Release $TAG published: https://github.com/dahai80/fusion-bench/releases/tag/$TAG"
