"""SPS profile -> bench-site submission (#43 AC3).

Maps one sweep profile onto bench-site's `benchmarks` table: one row per
(width, batch_size) candidate with benchmark_type="sps", the median
tokens/wall-time as the headline metric, and the full candidate +
provenance in `detail` so retunes stay comparable on bench.dpdns.org.
"""

from __future__ import annotations

import json
import logging
import re

from ..reporter.bench_site_db import BenchSiteDB, BenchSiteRecord
from .profile import SpsProfile

logger = logging.getLogger(__name__)

_QUANT_RE = re.compile(r"(\d+bit)", re.IGNORECASE)


def _quant_from_model(model: str) -> str:
    m = _QUANT_RE.search(model)
    return m.group(1).lower() if m else "native"


def profile_to_records(profile: SpsProfile) -> list[BenchSiteRecord]:
    records: list[BenchSiteRecord] = []
    for row in profile.table:
        detail = {
            "width": row.get("width"),
            "batch_size": row.get("batch_size"),
            "width_applied_rate": row.get("width_applied_rate"),
            "repeats_tok_s": row.get("repeats_tok_s"),
            "acceptance_length": profile.acceptance_length,
            "engine_spec_support": profile.engine_spec_support,
            "engine_base_url": profile.engine_base_url,
            "input_digest": profile.input_digest,
            "best_table": profile.best,
            "generated_at": profile.generated_at,
        }
        records.append(
            BenchSiteRecord(
                chip_name=profile.chip or "unknown",
                memory_gb=int(profile.ram_gb or 0),
                os_version="macOS",
                omlx_version=profile.engine_version or "fusion-mlx",
                model_name=profile.model,
                quantization=_quant_from_model(profile.model),
                context_length=0,
                benchmark_type="sps",
                task_name="sps-tune",
                metric_name=f"median_tok_s_w{row.get('width')}_b{row.get('batch_size')}",
                metric_value=float(row.get("median_tok_s", 0.0)),
                detail=json.dumps(detail, ensure_ascii=False),
                submission_group=f"sps-{profile.input_digest or 'untagged'}",
            )
        )
    return records


def submit_profile(profile: SpsProfile, db_path: str = "") -> int:
    # Writes to the local bench-site DB (primary path); remote HTTP
    # submission rides BenchSiteSubmitter separately if needed.
    db = BenchSiteDB(db_path)
    try:
        n = 0
        for rec in profile_to_records(profile):
            db.insert(rec)
            n += 1
        logger.info("SPS profile submitted to bench-site: %d rows", n)
        return n
    finally:
        db.close() if hasattr(db, "close") else None


__all__ = ["profile_to_records", "submit_profile"]
