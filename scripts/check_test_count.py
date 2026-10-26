# Test-count drift guard (issue #30, security#43 pattern, exact-match).
# Recomputes the real test count via `pytest --collect-only -q` and fails if
# a README Tests badge number drifts by even 1. Badges must be recomputable
# from a real run, not hand-edited and forgotten.
#
# CI post-step: python scripts/check_test_count.py
# Local regen:  pytest --collect-only -q | tail -1

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BADGE_PATTERNS = {
    "README.md": r"badge/Tests-(\d+)-success",
    "README_CN.md": r"badge/Tests-(\d+)-success",
}


def collect_actual_count() -> int:
    result = subprocess.run(
        ["pytest", "--collect-only", "-q"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=300,
    )
    output = result.stdout + result.stderr
    match = re.search(r"(\d+) tests? collected", output)
    if not match:
        print(f"[check-test-count] cannot parse pytest output:\n{output[-500:]}", file=sys.stderr)
        return -1
    return int(match.group(1))


def read_badge_count(readme: str) -> int:
    path = REPO_ROOT / readme
    if not path.exists():
        print(f"[check-test-count] {readme}: not present, skipping")
        return -2
    text = path.read_text(encoding="utf-8")
    match = re.search(BADGE_PATTERNS[readme], text)
    if not match:
        print(f"[check-test-count] {readme}: Tests badge not found (pattern {BADGE_PATTERNS[readme]})", file=sys.stderr)
        return -1
    return int(match.group(1))


def main() -> int:
    actual = collect_actual_count()
    if actual < 0:
        return 1
    print(f"[check-test-count] actual collected tests: {actual}")
    failed = False
    for readme in BADGE_PATTERNS:
        claimed = read_badge_count(readme)
        if claimed == -2:
            continue
        if claimed < 0:
            failed = True
            continue
        if claimed != actual:
            print(
                f"[check-test-count] {readme}: badge says {claimed}, actual {actual} "
                f"(drift {claimed - actual:+d}). Fix: https://img.shields.io/badge/Tests-{actual}-success.svg",
                file=sys.stderr,
            )
            failed = True
        else:
            print(f"[check-test-count] {readme}: badge {claimed} == actual {actual} OK")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
