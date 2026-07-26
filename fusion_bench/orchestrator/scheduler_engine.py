"""APScheduler integration — scheduled/cron-triggered benchmark tasks.

Imported by CLI cmd_schedule and API /schedules endpoints.
Schema: SchedulerConfig with cron expression + TaskCreateRequest params.
User instruction: "把所有没完全做完，没启动做，有差距的全部启动补齐" (P1-5).
"""

from __future__ import annotations

import contextlib
import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_DB_PATH = Path.home() / ".fusion-bench" / "schedules.db"


class SchedulerConfig:
    """A scheduled benchmark trigger configuration."""

    def __init__(
        self,
        schedule_id: str = "",
        name: str = "",
        cron: str = "",
        model: str = "qwen3.5-9b",
        executor_key: str = "speed",
        level: str = "L1",
        params: dict[str, Any] | None = None,
        enabled: bool = True,
    ):
        self.schedule_id = schedule_id or f"sched-{int(time.time())}"
        self.name = name
        self.cron = cron
        self.model = model
        self.executor_key = executor_key
        self.level = level
        self.params = params or {}
        self.enabled = enabled
        self.created_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        self.last_run_at = ""
        self.last_task_id = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schedule_id": self.schedule_id,
            "name": self.name,
            "cron": self.cron,
            "model": self.model,
            "executor_key": self.executor_key,
            "level": self.level,
            "params": self.params,
            "enabled": self.enabled,
            "created_at": self.created_at,
            "last_run_at": self.last_run_at,
            "last_task_id": self.last_task_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SchedulerConfig:
        cfg = cls(
            schedule_id=data.get("schedule_id", ""),
            name=data.get("name", ""),
            cron=data.get("cron", ""),
            model=data.get("model", "qwen3.5-9b"),
            executor_key=data.get("executor_key", "speed"),
            level=data.get("level", "L1"),
            params=data.get("params", {}),
            enabled=data.get("enabled", True),
        )
        cfg.created_at = data.get("created_at", cfg.created_at)
        cfg.last_run_at = data.get("last_run_at", "")
        cfg.last_task_id = data.get("last_task_id", "")
        return cfg


class ScheduleStore:
    """SQLite-backed schedule store for cron-triggered benchmarks."""

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path) if db_path else _DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._ensure_table()

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
        return self._conn

    def _ensure_table(self) -> None:
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS schedules (
                schedule_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                cron TEXT NOT NULL,
                model TEXT NOT NULL,
                executor_key TEXT NOT NULL,
                level TEXT NOT NULL DEFAULT 'L1',
                params TEXT DEFAULT '{}',
                enabled INTEGER DEFAULT 1,
                created_at TEXT NOT NULL,
                last_run_at TEXT DEFAULT '',
                last_task_id TEXT DEFAULT ''
            )
        """)
        self.conn.commit()

    def add(self, config: SchedulerConfig) -> str:
        try:
            self.conn.execute(
                """INSERT OR REPLACE INTO schedules
                   (schedule_id, name, cron, model, executor_key, level, params,
                    enabled, created_at, last_run_at, last_task_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    config.schedule_id,
                    config.name,
                    config.cron,
                    config.model,
                    config.executor_key,
                    config.level,
                    json.dumps(config.params),
                    1 if config.enabled else 0,
                    config.created_at,
                    config.last_run_at,
                    config.last_task_id,
                ),
            )
            self.conn.commit()
            logger.info("Schedule added: %s (%s)", config.name, config.cron)
            return config.schedule_id
        except sqlite3.Error as e:
            logger.error("Failed to add schedule %s: %s", config.name, e)
            return ""

    def get(self, schedule_id: str) -> SchedulerConfig | None:
        row = self.conn.execute(
            "SELECT * FROM schedules WHERE schedule_id = ?",
            (schedule_id,),
        ).fetchone()
        if not row:
            return None
        return self._row_to_config(row)

    def list_schedules(self, enabled_only: bool = False) -> list[SchedulerConfig]:
        q = "SELECT * FROM schedules"
        if enabled_only:
            q += " WHERE enabled = 1"
        q += " ORDER BY created_at DESC"
        rows = self.conn.execute(q).fetchall()
        return [self._row_to_config(r) for r in rows]

    def update_last_run(self, schedule_id: str, task_id: str) -> None:
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        self.conn.execute(
            "UPDATE schedules SET last_run_at = ?, last_task_id = ? WHERE schedule_id = ?",
            (now, task_id, schedule_id),
        )
        self.conn.commit()

    def toggle(self, schedule_id: str, enabled: bool) -> bool:
        cursor = self.conn.execute(
            "UPDATE schedules SET enabled = ? WHERE schedule_id = ?",
            (1 if enabled else 0, schedule_id),
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def delete(self, schedule_id: str) -> bool:
        cursor = self.conn.execute(
            "DELETE FROM schedules WHERE schedule_id = ?",
            (schedule_id,),
        )
        self.conn.commit()
        return cursor.rowcount > 0

    @staticmethod
    def _row_to_config(row: sqlite3.Row) -> SchedulerConfig:
        params = {}
        if row["params"]:
            with contextlib.suppress(json.JSONDecodeError):
                params = json.loads(row["params"])
        cfg = SchedulerConfig(
            schedule_id=row["schedule_id"],
            name=row["name"],
            cron=row["cron"],
            model=row["model"],
            executor_key=row["executor_key"],
            level=row["level"],
            params=params,
            enabled=bool(row["enabled"]),
        )
        cfg.created_at = row["created_at"]
        cfg.last_run_at = row["last_run_at"] or ""
        cfg.last_task_id = row["last_task_id"] or ""
        return cfg

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None


def parse_cron(cron_expr: str) -> dict[str, str]:
    parts = cron_expr.strip().split()
    if len(parts) != 5:
        raise ValueError(f"Invalid cron expression: {cron_expr!r} (expected 5 fields)")
    return {
        "minute": parts[0],
        "hour": parts[1],
        "day_of_month": parts[2],
        "month": parts[3],
        "day_of_week": parts[4],
    }


def cron_to_description(cron_expr: str) -> str:
    try:
        p = parse_cron(cron_expr)
    except ValueError:
        return cron_expr
    if p["minute"] == "0" and p["hour"].startswith("*/"):
        return f"Every {p['hour'][2:]} hours on the hour"
    if p["minute"] == "0" and p["hour"] != "*":
        return f"Daily at {p['hour']}:00"
    if p["minute"] != "*" and p["hour"] == "*":
        return f"Every hour at :{p['minute']}"
    if p["day_of_week"] != "*" and p["hour"] != "*":
        days = {
            "0": "Sunday",
            "1": "Monday",
            "2": "Tuesday",
            "3": "Wednesday",
            "4": "Thursday",
            "5": "Friday",
            "6": "Saturday",
        }
        day = days.get(p["day_of_week"], p["day_of_week"])
        return f"Weekly on {day} at {p['hour']}:{p['minute']}"
    return f"Cron: {cron_expr}"
