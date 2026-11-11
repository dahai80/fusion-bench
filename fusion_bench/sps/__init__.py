"""Issue #43 — SPS (speculative decoding) tuning suite.

Benchmark-driven draft-token budget tuning for fusion-mlx speculative
decoding, generalized from Tencent DSpine's tune_sps.py pattern
(Apache-2.0). Sweeps draft widths x batch sizes against the live engine,
scores by median output tokens / wall time, and emits a versioned
profile (fusion-bench.sps/v1) with full provenance.

Engine coupling note: per-request speculative params are NOT yet
accepted by fusion-mlx (upstream #1528). Widths are transported in the
request body ("speculative": {"draft_tokens": W}); the engine applies
them once support lands, and the sweep degrades gracefully to the
batch-size axis until then. Acceptance length is captured from engine
metrics when exposed, null otherwise.
"""

from .prefixes import SPrefix, load_prefixes
from .profile import SCHEMA_VERSION, SpsProfile, current_hardware, file_digest, is_stale
from .tuner import SpsCandidateResult, SpsConfig, SpsTuner

__all__ = [
    "SCHEMA_VERSION",
    "SPrefix",
    "SpsCandidateResult",
    "SpsConfig",
    "SpsProfile",
    "SpsTuner",
    "current_hardware",
    "file_digest",
    "is_stale",
    "load_prefixes",
]
