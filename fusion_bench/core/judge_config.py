"""Judge model configuration — LLM-as-judge evaluation settings (canonical).

Importers/callers: api/app.py /judges endpoints; executors that use LLM-as-judge
blend (agent/artifact); cli.py judge subcommand; judge/ package re-exports.
Affected API: /judges CRUD endpoints (GET/POST/DELETE); judge CLI subcommand.
Data schema: JudgeConfig dataclass (name, model, judge_type, weight, criteria,
rubric, temperature, prompt_template, score_range, max_tokens); judges table
(name PK, model, judge_type, weight, criteria JSON, rubric, temperature,
prompt_template, score_range JSON, max_tokens, created_at).
Canonical source of truth — judge/config.py + storage/judge_store.py re-export.
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

_DEFAULT_DB_PATH = Path.home() / ".fusion-bench" / "judges.db"


class JudgeConfig:
    """Configuration for an LLM-as-judge evaluator (canonical)."""

    def __init__(
        self,
        name: str = "",
        model: str = "qwen3.5-9b",
        judge_type: str = "hybrid",
        weight: float = 0.5,
        criteria: list[str] | None = None,
        rubric: str = "",
        temperature: float = 0.0,
        prompt_template: str = "",
        score_range: tuple[float, float] = (0.0, 1.0),
        max_tokens: int = 1024,
    ):
        self.name = name
        self.model = model
        self.judge_type = judge_type
        self.weight = weight
        self.criteria = criteria or []
        self.rubric = rubric
        self.temperature = temperature
        self.prompt_template = prompt_template or self._default_template()
        self.score_range = score_range
        self.max_tokens = max_tokens
        self.created_at = time.strftime("%Y-%m-%dT%H:%M:%S")

    @staticmethod
    def _default_template() -> str:
        return (
            "Evaluate the following response based on the given criteria.\n\n"
            "Question: {question}\n"
            "Response: {response}\n\n"
            "Criteria: {criteria}\n\n"
            "Provide a score between {min_score} and {max_score} "
            "and a brief justification."
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "model": self.model,
            "judge_type": self.judge_type,
            "weight": self.weight,
            "criteria": self.criteria,
            "rubric": self.rubric,
            "temperature": self.temperature,
            "prompt_template": self.prompt_template,
            "score_range": list(self.score_range),
            "max_tokens": self.max_tokens,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JudgeConfig:
        cfg = cls(
            name=data.get("name", ""),
            model=data.get("model", "qwen3.5-9b"),
            judge_type=data.get("judge_type", "hybrid"),
            weight=data.get("weight", 0.5),
            criteria=data.get("criteria"),
            rubric=data.get("rubric", ""),
            temperature=data.get("temperature", 0.0),
            prompt_template=data.get("prompt_template", ""),
            score_range=tuple(data.get("score_range", [0.0, 1.0])),
            max_tokens=data.get("max_tokens", 1024),
        )
        cfg.created_at = data.get("created_at", cfg.created_at)
        return cfg


class JudgeStore:
    """SQLite-backed judge configuration store (name-keyed, canonical)."""

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
            CREATE TABLE IF NOT EXISTS judges (
                name TEXT PRIMARY KEY,
                model TEXT NOT NULL,
                judge_type TEXT NOT NULL DEFAULT 'hybrid',
                weight REAL NOT NULL DEFAULT 0.5,
                criteria TEXT NOT NULL DEFAULT '[]',
                rubric TEXT NOT NULL DEFAULT '',
                temperature REAL DEFAULT 0.0,
                prompt_template TEXT NOT NULL DEFAULT '',
                score_range TEXT DEFAULT '[0.0, 1.0]',
                max_tokens INTEGER DEFAULT 1024,
                created_at TEXT NOT NULL
            )
        """)
        self.conn.commit()

    def save(self, name: str, config: JudgeConfig) -> None:
        config.name = name
        self.conn.execute(
            """INSERT OR REPLACE INTO judges
               (name, model, judge_type, weight, criteria, rubric, temperature,
                prompt_template, score_range, max_tokens, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                name,
                config.model,
                config.judge_type,
                config.weight,
                json.dumps(config.criteria),
                config.rubric,
                config.temperature,
                config.prompt_template,
                json.dumps(list(config.score_range)),
                config.max_tokens,
                config.created_at,
            ),
        )
        self.conn.commit()
        logger.info("Judge config saved: %s (type=%s, model=%s)", name, config.judge_type, config.model)

    def get(self, name: str) -> JudgeConfig | None:
        row = self.conn.execute("SELECT * FROM judges WHERE name = ?", (name,)).fetchone()
        if not row:
            return None
        return self._row_to_config(row)

    def list(self) -> list[str]:
        rows = self.conn.execute("SELECT name FROM judges ORDER BY name").fetchall()
        return [r["name"] for r in rows]

    def delete(self, name: str) -> bool:
        cursor = self.conn.execute("DELETE FROM judges WHERE name = ?", (name,))
        self.conn.commit()
        return cursor.rowcount > 0

    @staticmethod
    def _row_to_config(row: sqlite3.Row) -> JudgeConfig:
        criteria: list[str] = []
        if row["criteria"]:
            with contextlib.suppress(json.JSONDecodeError):
                criteria = json.loads(row["criteria"])
        score_range = (0.0, 1.0)
        if row["score_range"]:
            try:
                sr = json.loads(row["score_range"])
                score_range = tuple(sr)
            except (json.JSONDecodeError, TypeError):
                pass
        cfg = JudgeConfig(
            name=row["name"],
            model=row["model"],
            judge_type=row["judge_type"],
            weight=row["weight"],
            criteria=criteria,
            rubric=row["rubric"],
            temperature=row["temperature"],
            prompt_template=row["prompt_template"],
            score_range=score_range,
            max_tokens=row["max_tokens"],
        )
        cfg.created_at = row["created_at"]
        return cfg

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
