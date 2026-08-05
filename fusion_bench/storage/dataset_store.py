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

SUPPORTED_FORMATS = ("sharegpt", "alpaca", "messages")
_VALID_ROLES = {"system", "user", "assistant", "tool", "function"}


def _validate_sharegpt(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """ShareGPT: each item has 'conversations': list of {from, value}."""
    items: list[dict[str, Any]] = []
    for i, row in enumerate(raw):
        convs = row.get("conversations")
        if not isinstance(convs, list) or not convs:
            raise ValueError(f"sharegpt item {i}: missing 'conversations' list")
        messages = []
        for j, c in enumerate(convs):
            if not isinstance(c, dict) or "from" not in c or "value" not in c:
                raise ValueError(f"sharegpt item {i} turn {j}: need 'from' and 'value'")
            role = str(c["from"]).lower()
            if role not in _VALID_ROLES:
                logger.warning("sharegpt item %d turn %d: role '%s' non-standard", i, j, role)
            messages.append({"role": role, "content": str(c["value"])})
        items.append({"messages": messages})
    return items


def _validate_alpaca(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Alpaca: each item has 'instruction' (+ optional 'input', 'output')."""
    items: list[dict[str, Any]] = []
    for i, row in enumerate(raw):
        if not isinstance(row, dict) or "instruction" not in row:
            raise ValueError(f"alpaca item {i}: missing 'instruction'")
        instruction = str(row["instruction"])
        inp = str(row.get("input", "")).strip()
        output = str(row.get("output", ""))
        user_content = instruction + (f"\n{inp}" if inp else "")
        messages = [
            {"role": "user", "content": user_content},
            {"role": "assistant", "content": output},
        ]
        items.append({"messages": messages})
    return items


def _validate_messages(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """messages-JSONL: each item has 'messages': list of {role, content}."""
    items: list[dict[str, Any]] = []
    for i, row in enumerate(raw):
        msgs = row.get("messages")
        if not isinstance(msgs, list) or not msgs:
            raise ValueError(f"messages item {i}: missing 'messages' list")
        messages = []
        for j, m in enumerate(msgs):
            if not isinstance(m, dict) or "role" not in m or "content" not in m:
                raise ValueError(f"messages item {i} turn {j}: need 'role' and 'content'")
            role = str(m["role"]).lower()
            if role not in _VALID_ROLES:
                logger.warning("messages item %d turn %d: role '%s' non-standard", i, j, role)
            messages.append({"role": role, "content": str(m["content"])})
        extra = {k: v for k, v in row.items() if k != "messages"}
        items.append({"messages": messages, **extra})
    return items


_FORMAT_VALIDATORS = {
    "sharegpt": _validate_sharegpt,
    "alpaca": _validate_alpaca,
    "messages": _validate_messages,
}


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

    @staticmethod
    def validate_format(fmt: str, raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Validate raw items against a named format; returns normalized items.

        Supported formats: sharegpt, alpaca, messages. Raises ValueError on
        schema mismatch. Each normalized item is {"messages": [{"role","content"}, ...]}.
        """
        fmt_norm = fmt.lower().strip()
        validator = _FORMAT_VALIDATORS.get(fmt_norm)
        if validator is None:
            raise ValueError(f"unsupported format '{fmt}'; supported: {', '.join(SUPPORTED_FORMATS)}")
        if not isinstance(raw, list):
            raise ValueError("dataset payload must be a list of objects")
        return validator(raw)

    def load_dataset_file(
        self,
        path: str | Path,
        format: str,
        name: str,
        description: str = "",
    ) -> str:
        """Load a standard-format dataset file (JSON or JSONL), validate, and store.

        Supports ShareGPT / Alpaca / messages-JSONL. JSONL files have one JSON
        object per line; JSON files are a single list of objects. Returns the
        new dataset_id, or "" on failure.
        """
        p = Path(path)
        if not p.is_file():
            logger.error("Dataset file not found: %s", p)
            return ""
        try:
            text = p.read_text(encoding="utf-8")
        except OSError as e:
            logger.error("Failed to read dataset file %s: %s", p, e)
            return ""

        raw: list[dict[str, Any]]
        if p.suffix.lower() == ".jsonl":
            raw = []
            for lineno, line in enumerate(text.splitlines(), 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    raw.append(json.loads(line))
                except json.JSONDecodeError as e:
                    logger.error("JSONL parse error at %s:%d: %s", p, lineno, e)
                    return ""
        else:
            try:
                loaded = json.loads(text)
            except json.JSONDecodeError as e:
                logger.error("JSON parse error in %s: %s", p, e)
                return ""
            if not isinstance(loaded, list):
                logger.error("Dataset file %s must contain a JSON list", p)
                return ""
            raw = loaded

        try:
            items = self.validate_format(format, raw)
        except ValueError as e:
            logger.error("Dataset %s format validation failed: %s", format, e)
            return ""

        ds_id = self.create(name=name, items=items, description=description, format=format.lower())
        if ds_id:
            logger.info(
                "Loaded %d items from %s (format=%s, dataset_id=%s)",
                len(items),
                p,
                format,
                ds_id,
            )
        return ds_id
