"""Dataset store — manages custom evaluation datasets.

Importers/callers: api/app.py /datasets endpoints; cli.py cmd_dataset.
Affected API: /datasets CRUD endpoints (GET/POST/PUT/DELETE).
Data schema: datasets table (dataset_id PK, name, description, format, items JSON, item_count, created_at, updated_at).
User instruction: "把所有没完全做完，没启动做，有差距的全部启动补齐" (P2-15 custom dataset upload).
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

_DEFAULT_DB_PATH = Path.home() / ".fusion-bench" / "datasets.db"


class DatasetStore:
    """SQLite-backed custom dataset store."""

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
            CREATE TABLE IF NOT EXISTS datasets (
                dataset_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                format TEXT NOT NULL DEFAULT 'qa',
                items TEXT NOT NULL DEFAULT '[]',
                item_count INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        self.conn.commit()

    def create(
        self,
        name: str,
        items: list[dict[str, Any]],
        description: str = "",
        format: str = "qa",
    ) -> str:
        dataset_id = f"ds-{uuid.uuid4().hex[:8]}"
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        try:
            self.conn.execute(
                """INSERT INTO datasets
                   (dataset_id, name, description, format, items, item_count, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    dataset_id,
                    name,
                    description,
                    format,
                    json.dumps(items, ensure_ascii=False),
                    len(items),
                    now,
                    now,
                ),
            )
            self.conn.commit()
            logger.info("Dataset created: %s (%d items)", name, len(items))
            return dataset_id
        except sqlite3.Error as e:
            logger.error("Failed to create dataset %s: %s", name, e)
            return ""

    def get(self, dataset_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM datasets WHERE dataset_id = ?", (dataset_id,)).fetchone()
        if not row:
            return None
        items = []
        if row["items"]:
            with contextlib.suppress(json.JSONDecodeError):
                items = json.loads(row["items"])
        return {
            "dataset_id": row["dataset_id"],
            "name": row["name"],
            "description": row["description"],
            "format": row["format"],
            "items": items,
            "item_count": row["item_count"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def list_datasets(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT dataset_id, name, description, format, item_count, created_at FROM datasets ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def update(self, dataset_id: str, **kwargs: Any) -> bool:
        sets = []
        params: list[Any] = []
        for key in ("name", "description", "format"):
            if key in kwargs:
                sets.append(f"{key} = ?")
                params.append(kwargs[key])
        if "items" in kwargs:
            sets.append("items = ?")
            sets.append("item_count = ?")
            params.append(json.dumps(kwargs["items"], ensure_ascii=False))
            params.append(len(kwargs["items"]))
        if not sets:
            return False
        sets.append("updated_at = ?")
        params.append(time.strftime("%Y-%m-%dT%H:%M:%S"))
        params.append(dataset_id)
        cursor = self.conn.execute(
            f"UPDATE datasets SET {', '.join(sets)} WHERE dataset_id = ?",
            params,
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def delete(self, dataset_id: str) -> bool:
        cursor = self.conn.execute("DELETE FROM datasets WHERE dataset_id = ?", (dataset_id,))
        self.conn.commit()
        return cursor.rowcount > 0

    def get_items(self, dataset_id: str) -> list[dict[str, Any]]:
        row = self.conn.execute("SELECT items FROM datasets WHERE dataset_id = ?", (dataset_id,)).fetchone()
        if not row or not row["items"]:
            return []
        try:
            return json.loads(row["items"])
        except json.JSONDecodeError:
            return []

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
