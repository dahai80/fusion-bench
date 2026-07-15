"""BenchSite database writer — writes Fusion-Bench results directly to bench-site's SQLite database.

This is the primary integration point between Fusion-Bench (benchmarking engine)
and bench-site (web UI at bench.dpdns.org). Fusion-Bench runs benchmarks and
writes results directly to bench-site's database, eliminating the need for a
separate API submission step.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..engine.benchmark import SpeedMetrics, BenchmarkResult

logger = logging.getLogger(__name__)


@dataclass
class BenchSiteRecord:
    """A single benchmark record matching bench-site's database schema."""

    chip_name: str
    chip_variant: str = ""
    memory_gb: int = 0
    gpu_cores: int = 0
    os_version: str = ""
    omlx_version: str = "fusion-mlx"

    model_name: str = ""
    quantization: str = "mxfp8"
    context_length: int = 4096

    pp_tps: float = 0.0
    tg_tps: float = 0.0
    ttft_ms: float | None = None
    peak_memory_gb: float | None = None

    batching_results: str = ""
    owner_hash: str = ""
    submission_group: str = "fusion-bench"


class BenchSiteDB:
    """Writes Fusion-Bench results directly to bench-site's SQLite database.

    This is the core integration: Fusion-Bench runs benchmarks and writes
    results directly into bench-site's database, making them immediately
    available on the bench.dpdns.org web UI.
    """

    def __init__(self, db_path: str = ""):
        if not db_path:
            # Default bench-site database location
            candidates = [
                Path.home() / "claude-home" / "bench-site" / "data" / "bench.db",
                Path("/Users/dahai/claude-home/bench-site/data/bench.db"),
            ]
            for c in candidates:
                if c.exists():
                    db_path = str(c)
                    break
            if not db_path:
                # Fallback: create a local copy
                db_path = str(Path.home() / ".fusion-bench" / "bench-site.db")
                Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self._conn: sqlite3.Connection | None = None

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _ensure_schema(self) -> None:
        """Ensure bench-site schema exists (creates table if missing)."""
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS benchmarks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT DEFAULT (datetime('now')) NOT NULL,
                chip_name TEXT NOT NULL,
                chip_variant TEXT DEFAULT '',
                memory_gb INTEGER NOT NULL,
                gpu_cores INTEGER NOT NULL,
                os_version TEXT DEFAULT '',
                omlx_version TEXT DEFAULT '',
                model_name TEXT NOT NULL,
                quantization TEXT NOT NULL,
                context_length INTEGER NOT NULL,
                pp_tps REAL NOT NULL,
                tg_tps REAL NOT NULL,
                ttft_ms REAL,
                peak_memory_gb REAL,
                batching_results TEXT DEFAULT '',
                owner_hash TEXT DEFAULT '',
                submission_group TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_bench_model ON benchmarks(model_name, quantization);
            CREATE INDEX IF NOT EXISTS idx_bench_chip ON benchmarks(chip_name, memory_gb);
            CREATE INDEX IF NOT EXISTS idx_bench_created ON benchmarks(created_at);
        """)
        conn.commit()

    def insert(self, record: BenchSiteRecord) -> int:
        """Insert a benchmark record into bench-site database. Returns the new row ID."""
        self._ensure_schema()
        conn = self._get_conn()
        cursor = conn.execute(
            """INSERT INTO benchmarks
               (chip_name, chip_variant, memory_gb, gpu_cores, os_version, omlx_version,
                model_name, quantization, context_length,
                pp_tps, tg_tps, ttft_ms, peak_memory_gb,
                batching_results, owner_hash, submission_group)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record.chip_name, record.chip_variant, record.memory_gb,
                record.gpu_cores, record.os_version, record.omlx_version,
                record.model_name, record.quantization, record.context_length,
                record.pp_tps, record.tg_tps, record.ttft_ms,
                record.peak_memory_gb, record.batching_results,
                record.owner_hash, record.submission_group,
            ),
        )
        conn.commit()
        return cursor.lastrowid or 0

    def insert_from_metrics(
        self,
        metrics: SpeedMetrics,
        model_name: str,
        quantization: str = "mxfp8",
        context_length: int = 4096,
        hw_info: dict | None = None,
        owner_hash: str = "",
    ) -> int:
        """Insert a SpeedMetrics result directly into bench-site DB."""
        if hw_info is None:
            hw_info = self._detect_hardware()
        record = BenchSiteRecord(
            chip_name=hw_info.get("chip_name", "Apple Silicon"),
            chip_variant=hw_info.get("chip_variant", ""),
            memory_gb=hw_info.get("memory_gb", 0),
            gpu_cores=hw_info.get("gpu_cores", 0),
            os_version=hw_info.get("os_version", ""),
            model_name=model_name,
            quantization=quantization,
            context_length=context_length,
            pp_tps=round(metrics.prefill_speed, 2),
            tg_tps=round(metrics.decode_speed, 2),
            ttft_ms=round(metrics.prefill_time * 1000, 2) if metrics.prefill_time > 0 else None,
            peak_memory_gb=round(metrics.peak_memory_mb / 1024, 2) if metrics.peak_memory_mb > 0 else None,
            owner_hash=owner_hash,
        )
        return self.insert(record)

    def insert_from_benchmark(
        self,
        result: BenchmarkResult,
        hw_info: dict | None = None,
        owner_hash: str = "",
    ) -> int:
        """Insert a BenchmarkResult directly into bench-site DB."""
        # Extract quantization from model name
        model_parts = result.model.split("-")
        quant = "mxfp8"
        for part in model_parts:
            if any(q in part.lower() for q in ["mxfp", "quant", "mixed"]):
                quant = part
                break
        base_model = result.model.replace(f"-{quant}", "") if quant != "mxfp8" else result.model
        return self.insert_from_metrics(
            metrics=result.metrics,
            model_name=base_model,
            quantization=quant,
            context_length=result.config.get("max_tokens", 4096),
            hw_info=hw_info,
            owner_hash=owner_hash,
        )

    def query(self, model: str = "", chip: str = "", limit: int = 50) -> list[dict[str, Any]]:
        """Query benchmark records from bench-site database."""
        conn = self._get_conn()
        conditions = []
        params = []
        if model:
            conditions.append("model_name LIKE ?")
            params.append(f"%{model}%")
        if chip:
            conditions.append("chip_name LIKE ?")
            params.append(f"%{chip}%")
        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        rows = conn.execute(
            f"SELECT * FROM benchmarks {where} ORDER BY created_at DESC LIMIT ?",
            params + [limit],
        ).fetchall()
        return [dict(r) for r in rows]

    def stats(self) -> dict[str, Any]:
        """Get database statistics."""
        self._ensure_schema()
        conn = self._get_conn()
        total = conn.execute("SELECT COUNT(*) as cnt FROM benchmarks").fetchone()
        models = conn.execute("SELECT COUNT(DISTINCT model_name) as cnt FROM benchmarks").fetchone()
        chips = conn.execute("SELECT COUNT(DISTINCT chip_name) as cnt FROM benchmarks").fetchone()
        return {
            "total_entries": total["cnt"] if total else 0,
            "unique_models": models["cnt"] if models else 0,
            "unique_chips": chips["cnt"] if chips else 0,
            "database_path": self.db_path,
        }

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    @staticmethod
    def _detect_hardware() -> dict[str, Any]:
        """Auto-detect Apple Silicon hardware specs."""
        import platform
        import subprocess
        info = {"chip_name": "Apple Silicon", "chip_variant": "", "memory_gb": 0, "gpu_cores": 0, "os_version": ""}
        try:
            result = subprocess.run(
                ["system_profiler", "SPDisplaysDataType", "-json"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                displays = data.get("SPDisplaysDataType", [])
                if displays:
                    gpu = displays[0]
                    info["chip_name"] = gpu.get("sppci_model", "").replace("Apple", "").strip() or "Apple Silicon"
                    cores = gpu.get("sppci_cores", 0)
                    info["gpu_cores"] = int(cores) if cores else 0
        except Exception:
            pass
        try:
            r = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, timeout=3)
            if r.returncode == 0:
                info["memory_gb"] = round(int(r.stdout.strip()) / (1024**3))
        except Exception:
            pass
        os_ver = platform.mac_ver()[0]
        info["os_version"] = f"macOS {os_ver}" if os_ver else ""
        return info