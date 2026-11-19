"""Golden eval set from production traffic (#49) — Loop B of the flywheel.

Ingest (stratified, privacy-gated) -> versioned golden cases -> PII scan
(CI-enforced) -> regression gate wired into the baseline compare machinery
-> Top-10 coverage KPI.
"""

from .cases import GoldenCase, load_cases, save_cases
from .coverage import coverage_kpi
from .gate import run_golden_gate
from .ingest import ingest_samples
from .pii_scan import scan_dir, scan_text

__all__ = [
    "GoldenCase",
    "load_cases",
    "save_cases",
    "coverage_kpi",
    "run_golden_gate",
    "ingest_samples",
    "scan_dir",
    "scan_text",
]
