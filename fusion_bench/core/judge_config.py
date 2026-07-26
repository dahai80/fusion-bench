"""Judge model configuration — LLM-as-judge evaluation settings.

Importers/callers: api/app.py /judges endpoints; executors that use LLM-as-judge pattern.
Affected API: /judges CRUD endpoints (GET/POST/DELETE).
Data schema: JudgeConfig dataclass (judge_id, name, model, prompt_template, criteria, score_range); judges table (judge_id PK, name, model, prompt_template, criteria JSON, score_range JSON, temperature, max_tokens, created_at).
User instruction: "把所有没完全做完，没启动做，有差距的全部启动补齐" (P2-16 judge model config).
"""

from __future__ import annotations

import contextlib
import json
import logging
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_DB_PATH = Path.home() / ".fusion-bench" / "judges.db"


class JudgeConfig:
    """Configuration for an LLM-as-judge evaluator."""

    def __init__(
        self,
        judge_id: str = "",
        name: str = "",
        model: str = "qwen3.5-9b",
        prompt_template: str = "",
        criteria: list[str] | None = None,
        score_range: tuple[float, float] = (0.0, 1.0),
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ):
        self.judge_id = judge_id or f"judge-{uuid.uuid4().hex[:8]}"
        self.name = name
        self.model = model
        self.prompt_template = prompt_template or self._default_template()
        self.criteria = criteria or ["relevance", "accuracy", "completeness"]
        self.score_range = score_range
        self.temperature = temperature
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
            "judge_id": self.judge_id,
            "name": self.name,
            "model": self.model,
            "prompt_template": self.prompt_template,
            "criteria": self.criteria,
            "score_range": list(self.score_range),
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JudgeConfig:
        cfg = cls(
            judge_id=data.get("judge_id", ""),
            name=data.get("name", ""),
            model=data.get("model", "qwen3.5-9b"),
            prompt_template=data.get("prompt_template", ""),
            criteria=data.get("criteria"),
            score_range=tuple(data.get("score_range", [0.0, 1.0])),
            temperature=data.get("temperature", 0.0),
            max_tokens=data.get("max_tokens", 1024),
        )
        cfg.created_at = data.get("created_at", cfg.created_at)
        return cfg


class JudgeStore:
    """SQLite-backed judge configuration store."""

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
                judge_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                model TEXT NOT NULL,
                prompt_template TEXT NOT NULL,
                criteria TEXT NOT NULL DEFAULT '[]',
                score_range TEXT DEFAULT '[0.0, 1.0]',
                temperature REAL DEFAULT 0.0,
                max_tokens INTEGER DEFAULT 1024,
                created_at TEXT NOT NULL
            )
        """)
        self.conn.commit()

    def add(self, config: JudgeConfig) -> str:
        try:
            self.conn.execute(
                """INSERT OR REPLACE INTO judges
                   (judge_id, name, model, prompt_template, criteria, score_range,
                    temperature, max_tokens, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    config.judge_id,
                    config.name,
                    config.model,
                    config.prompt_template,
                    json.dumps(config.criteria),
                    json.dumps(list(config.score_range)),
                    config.temperature,
                    config.max_tokens,
                    config.created_at,
                ),
            )
            self.conn.commit()
            logger.info("Judge config added: %s (%s)", config.name, config.model)
            return config.judge_id
        except sqlite3.Error as e:
            logger.error("Failed to add judge config %s: %s", config.name, e)
            return ""

    def get(self, judge_id: str) -> JudgeConfig | None:
        row = self.conn.execute("SELECT * FROM judges WHERE judge_id = ?", (judge_id,)).fetchone()
        if not row:
            return None
        return self._row_to_config(row)

    def list_judges(self) -> list[JudgeConfig]:
        rows = self.conn.execute("SELECT * FROM judges ORDER BY created_at DESC").fetchall()
        return [self._row_to_config(r) for r in rows]

    def delete(self, judge_id: str) -> bool:
        cursor = self.conn.execute("DELETE FROM judges WHERE judge_id = ?", (judge_id,))
        self.conn.commit()
        return cursor.rowcount > 0

    @staticmethod
    def _row_to_config(row: sqlite3.Row) -> JudgeConfig:
        criteria = []
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
            judge_id=row["judge_id"],
            name=row["name"],
            model=row["model"],
            prompt_template=row["prompt_template"],
            criteria=criteria,
            score_range=score_range,
            temperature=row["temperature"],
            max_tokens=row["max_tokens"],
        )
        cfg.created_at = row["created_at"]
        return cfg

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
