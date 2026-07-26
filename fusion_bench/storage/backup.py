"""Data backup - multi-copy backup and restore for SQLite databases.

Importers/callers: api/app.py /system/backup endpoint; cli.py cmd_backup subcommand.
Affected API: /system/backup POST endpoint; no data schema changes.
Data schema: reads .db files from ~/.fusion-bench/, copies to ~/.fusion-bench/backups/<label>/.
User instruction: "把所有没完全做完，没启动做，有差距的全部启动补齐" (P2-17 data multi-copy backup).
"""

from __future__ import annotations

import logging
import shutil
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_BACKUP_DIR = Path.home() / ".fusion-bench" / "backups"


class DataBackup:
    """Multi-copy backup for fusion-bench SQLite databases."""

    def __init__(self, backup_dir: str | Path | None = None):
        self.backup_dir = Path(backup_dir) if backup_dir else _DEFAULT_BACKUP_DIR
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def _db_paths(self) -> list[Path]:
        base = Path.home() / ".fusion-bench"
        return sorted(p for p in base.glob("*.db") if p.is_file())

    def backup(self, label: str = "") -> dict[str, Any]:
        ts = time.strftime("%Y%m%d-%H%M%S")
        label = label or ts
        dest_dir = self.backup_dir / label
        dest_dir.mkdir(parents=True, exist_ok=True)

        results: dict[str, Any] = {"label": label, "files": [], "errors": []}
        for db_path in self._db_paths():
            try:
                dest = dest_dir / db_path.name
                shutil.copy2(str(db_path), str(dest))
                results["files"].append(
                    {
                        "source": str(db_path),
                        "dest": str(dest),
                        "size_bytes": dest.stat().st_size,
                    }
                )
                logger.info("Backed up %s -> %s", db_path.name, dest)
            except Exception as e:
                results["errors"].append({"file": str(db_path), "error": str(e)})
                logger.error("Failed to backup %s: %s", db_path, e)

        results["total_files"] = len(results["files"])
        results["total_errors"] = len(results["errors"])
        logger.info(
            "Backup '%s' complete: %d files, %d errors",
            label,
            results["total_files"],
            results["total_errors"],
        )
        return results

    def restore(self, label: str, db_name: str = "") -> dict[str, Any]:
        src_dir = self.backup_dir / label
        if not src_dir.exists():
            return {"error": f"Backup label '{label}' not found"}

        results: dict[str, Any] = {"label": label, "files": [], "errors": []}
        base = Path.home() / ".fusion-bench"

        sources = [src_dir / db_name] if db_name else sorted(src_dir.glob("*.db"))
        for src in sources:
            if not src.exists():
                results["errors"].append({"file": str(src), "error": "Not found"})
                continue
            try:
                dest = base / src.name
                shutil.copy2(str(src), str(dest))
                results["files"].append(
                    {
                        "source": str(src),
                        "dest": str(dest),
                        "size_bytes": dest.stat().st_size,
                    }
                )
                logger.info("Restored %s -> %s", src.name, dest)
            except Exception as e:
                results["errors"].append({"file": str(src), "error": str(e)})
                logger.error("Failed to restore %s: %s", src, e)

        return results

    def list_backups(self) -> list[dict[str, Any]]:
        backups = []
        for d in sorted(self.backup_dir.iterdir()):
            if d.is_dir():
                files = list(d.glob("*.db"))
                backups.append(
                    {
                        "label": d.name,
                        "file_count": len(files),
                        "total_size": sum(f.stat().st_size for f in files),
                    }
                )
        return backups

    def delete_backup(self, label: str) -> bool:
        d = self.backup_dir / label
        if not d.exists():
            return False
        shutil.rmtree(str(d))
        logger.info("Deleted backup: %s", label)
        return True
