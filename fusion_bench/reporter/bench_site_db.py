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
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..engine.benchmark import BenchmarkResult, SpeedMetrics

logger = logging.getLogger(__name__)

_EXECUTOR_TYPE_MAP = {
    "speed": "speed",
    "model": "accuracy",
    "accuracy": "accuracy",
    "security": "security",
    "quant": "quant",
    "tune": "tune",
}


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

    benchmark_type: str = "speed"
    task_name: str = ""
    metric_name: str = "decode_speed"
    metric_value: float = 0.0
    detail: str = "{}"


class BenchSiteDB:
    """Writes Fusion-Bench results directly to bench-site's SQLite database.

    This is the core integration: Fusion-Bench runs benchmarks and writes
    results directly into bench-site's database, making them immediately
    available on the bench.dpdns.org web UI.
    """

    def __init__(self, db_path: str = ""):
        if not db_path:
            # Default bench-site database location
            # Priority: bench-site subdir in this project → legacy location → fallback
            project_bench_db = Path(__file__).resolve().parents[2] / "bench-site" / "data" / "bench.db"
            candidates = [
                project_bench_db,
                Path.home() / "claude-home" / "bench-site" / "data" / "bench.db",
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
                pp_tps REAL NOT NULL DEFAULT 0,
                tg_tps REAL NOT NULL DEFAULT 0,
                ttft_ms REAL,
                peak_memory_gb REAL,
                batching_results TEXT DEFAULT '',
                owner_hash TEXT DEFAULT '',
                submission_group TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_bench_model ON benchmarks(model_name, quantization);
            CREATE INDEX IF NOT EXISTS idx_bench_chip ON benchmarks(chip_name, memory_gb);
            CREATE INDEX IF NOT EXISTS idx_bench_owner ON benchmarks(owner_hash);
            CREATE INDEX IF NOT EXISTS idx_bench_created ON benchmarks(created_at);
        """)
        # Add new columns for multi-type support (safe for existing DBs)
        self._add_column_if_missing(conn, "benchmark_type", "TEXT NOT NULL DEFAULT 'speed'")
        self._add_column_if_missing(conn, "task_name", "TEXT DEFAULT ''")
        self._add_column_if_missing(conn, "metric_name", "TEXT DEFAULT 'decode_speed'")
        self._add_column_if_missing(conn, "metric_value", "REAL DEFAULT 0")
        self._add_column_if_missing(conn, "detail", "TEXT DEFAULT '{}'")
        conn.executescript("""
            CREATE INDEX IF NOT EXISTS idx_bench_type ON benchmarks(benchmark_type);
            CREATE INDEX IF NOT EXISTS idx_bench_task ON benchmarks(task_name);
        """)
        conn.commit()

    @staticmethod
    def _add_column_if_missing(conn: sqlite3.Connection, col: str, definition: str) -> None:
        """Add a column to benchmarks table if it does not exist.

        Only safe when called with hardcoded col/definition from _ensure_schema().
        Rejects any col or definition containing non-identifier characters.
        """
        import re

        if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", col):
            logger.error("_add_column_if_missing: invalid column name rejected: %r", col)
            return
        if not re.match(r"^[A-Za-z0-9_()' {}]+$", definition):
            logger.error("_add_column_if_missing: invalid definition rejected: %r", definition)
            return
        existing = {r[1] for r in conn.execute("PRAGMA table_info(benchmarks)").fetchall()}
        if col not in existing:
            logger.info("Adding column %s to benchmarks table", col)
            conn.execute(f"ALTER TABLE benchmarks ADD COLUMN {col} {definition}")

    def insert(self, record: BenchSiteRecord) -> int:
        """Insert a benchmark record into bench-site database. Returns the new row ID."""
        self._ensure_schema()
        conn = self._get_conn()
        cursor = conn.execute(
            """INSERT INTO benchmarks
               (chip_name, chip_variant, memory_gb, gpu_cores, os_version, omlx_version,
                model_name, quantization, context_length,
                pp_tps, tg_tps, ttft_ms, peak_memory_gb,
                batching_results, owner_hash, submission_group,
                benchmark_type, task_name, metric_name, metric_value, detail)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record.chip_name,
                record.chip_variant,
                record.memory_gb,
                record.gpu_cores,
                record.os_version,
                record.omlx_version,
                record.model_name,
                record.quantization,
                record.context_length,
                record.pp_tps,
                record.tg_tps,
                record.ttft_ms,
                record.peak_memory_gb,
                record.batching_results,
                record.owner_hash,
                record.submission_group,
                record.benchmark_type,
                record.task_name,
                record.metric_name,
                record.metric_value,
                record.detail,
            ),
        )
        conn.commit()
        return cursor.lastrowid or 0

    def insert_from_eval_result(
        self,
        eval_result: Any,
        model_name: str = "",
        hw_info: dict | None = None,
        owner_hash: str = "",
    ) -> int:
        """Insert an EvalResult from any executor into bench-site DB."""
        from ..core.plugin_base import EvalResult

        if not isinstance(eval_result, EvalResult):
            logger.error(
                "insert_from_eval_result: expected EvalResult, got %s",
                type(eval_result),
            )
            return 0

        if hw_info is None:
            hw_info = self._detect_hardware()

        btype = _EXECUTOR_TYPE_MAP.get(eval_result.executor_key, "speed")
        task_name = eval_result.task_id
        metric_name = eval_result.metric_name
        metric_value = eval_result.metric_value

        detail = self._build_detail(eval_result, btype)
        quantization = "mxfp8"
        pp_tps = 0.0
        tg_tps = 0.0
        ttft_ms = None
        peak_memory_gb = None

        if btype == "speed":
            for case in eval_result.cases:
                m = case.meta or {}
                if "decode_speed" in m:
                    tg_tps = m["decode_speed"]
                if "prefill_speed" in m:
                    pp_tps = m["prefill_speed"]
                if "peak_memory_mb" in m:
                    peak_memory_gb = round(m["peak_memory_mb"] / 1024, 2)
                if "prefill_time" in m and m["prefill_time"] > 0:
                    ttft_ms = round(m["prefill_time"] * 1000, 2)
                break

        record = BenchSiteRecord(
            chip_name=hw_info.get("chip_name", "Apple Silicon"),
            chip_variant=hw_info.get("chip_variant", ""),
            memory_gb=hw_info.get("memory_gb", 0),
            gpu_cores=hw_info.get("gpu_cores", 0),
            os_version=hw_info.get("os_version", ""),
            model_name=model_name or eval_result.model,
            quantization=quantization,
            context_length=4096,
            pp_tps=round(pp_tps, 2),
            tg_tps=round(tg_tps, 2),
            ttft_ms=ttft_ms,
            peak_memory_gb=peak_memory_gb,
            owner_hash=owner_hash,
            benchmark_type=btype,
            task_name=task_name,
            metric_name=metric_name,
            metric_value=round(metric_value, 4),
            detail=json.dumps(detail, ensure_ascii=False),
        )
        return self.insert(record)

    @staticmethod
    def _build_detail(eval_result: Any, btype: str) -> dict[str, Any]:
        """Build detail JSON dict from EvalResult based on benchmark type."""
        detail: dict[str, Any] = {}
        if btype == "speed":
            for case in eval_result.cases:
                m = case.meta or {}
                detail = {
                    "prefill_speed": m.get("prefill_speed", 0),
                    "decode_speed": m.get("decode_speed", 0),
                    "prefill_time_ms": round(m.get("prefill_time", 0) * 1000, 2),
                    "prompt_tokens": m.get("prompt_tokens", 0),
                    "completion_tokens": m.get("completion_tokens", 0),
                }
                break
        elif btype == "accuracy":
            detail = {
                "accuracy": eval_result.metric_value,
                "pass_rate": eval_result.pass_rate,
                "num_cases": len(eval_result.cases),
                "task_name": eval_result.task_id,
            }
            if eval_result.meta and isinstance(eval_result.meta, dict):
                detail["num_fewshot"] = eval_result.meta.get("num_fewshot", 0)
        elif btype == "security":
            safe_count = sum(1 for c in eval_result.cases if c.passed)
            probe_set = ""
            if eval_result.meta and isinstance(eval_result.meta, dict):
                probe_set = eval_result.meta.get("probe_set", "")
            detail = {
                "safety_rate": eval_result.metric_value,
                "probe_set": probe_set,
                "total_probes": len(eval_result.cases),
                "safe_count": safe_count,
            }
        elif btype == "quant":
            levels = []
            for case in eval_result.cases:
                m = case.meta or {}
                levels.append(
                    {
                        "quant": m.get("quant", ""),
                        "speed": m.get("speed", 0),
                        "memory_mb": m.get("memory_mb", 0),
                        "stable": m.get("stable", False),
                    }
                )
            detail = {"levels": levels}
            if eval_result.meta and isinstance(eval_result.meta, dict):
                detail["base_model"] = eval_result.meta.get("base_model", "")
        elif btype == "tune":
            meta = eval_result.meta or {}
            detail = {
                "best_config": meta.get("best_config", {}),
                "best_speed": meta.get("best_speed", eval_result.metric_value),
                "top3_configs": meta.get("top3_configs", []),
                "memory_saving_config": meta.get("memory_saving_config", {}),
                "balanced_config": meta.get("balanced_config", {}),
            }
        return detail

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
            benchmark_type="speed",
            metric_name="decode_speed",
            metric_value=round(metrics.decode_speed, 2),
            detail=json.dumps(
                {
                    "prefill_speed": metrics.prefill_speed,
                    "decode_speed": metrics.decode_speed,
                    "prefill_time_ms": round(metrics.prefill_time * 1000, 2),
                    "prompt_tokens": metrics.prompt_tokens,
                    "completion_tokens": metrics.completion_tokens,
                },
                ensure_ascii=False,
            ),
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

    def query(
        self,
        model: str = "",
        chip: str = "",
        benchmark_type: str = "",
        task_name: str = "",
        limit: int = 50,
    ) -> list[dict[str, Any]]:
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
        if benchmark_type:
            conditions.append("benchmark_type = ?")
            params.append(benchmark_type)
        if task_name:
            conditions.append("task_name = ?")
            params.append(task_name)
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
        type_rows = conn.execute(
            "SELECT benchmark_type, COUNT(*) as cnt FROM benchmarks GROUP BY benchmark_type"
        ).fetchall()
        by_type = {r["benchmark_type"]: r["cnt"] for r in type_rows}
        return {
            "total_entries": total["cnt"] if total else 0,
            "unique_models": models["cnt"] if models else 0,
            "unique_chips": chips["cnt"] if chips else 0,
            "by_type": by_type,
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

        info = {
            "chip_name": "Apple Silicon",
            "chip_variant": "",
            "memory_gb": 0,
            "gpu_cores": 0,
            "os_version": "",
        }
        try:
            result = subprocess.run(
                ["system_profiler", "SPDisplaysDataType", "-json"],
                capture_output=True,
                text=True,
                timeout=5,
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
            r = subprocess.run(
                ["sysctl", "-n", "hw.memsize"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            if r.returncode == 0:
                info["memory_gb"] = round(int(r.stdout.strip()) / (1024**3))
        except Exception:
            pass
        os_ver = platform.mac_ver()[0]
        info["os_version"] = f"macOS {os_ver}" if os_ver else ""
        return info
