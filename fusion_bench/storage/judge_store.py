"""SQLite store for named JudgeConfig definitions — re-exports canonical core store.

Canonical JudgeStore lives in fusion_bench.core.judge_config. This module
re-exports it so existing import paths (storage.judge_store) keep working.
"""

from __future__ import annotations

from fusion_bench.core.judge_config import _DEFAULT_DB_PATH, JudgeStore

__all__ = ["JudgeStore", "_DEFAULT_DB_PATH"]
