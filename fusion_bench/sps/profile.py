"""SPS profile artifact + provenance + staleness check (#43).

sps.json schema "fusion-bench.sps/v1": the sweep table plus provenance
(chip, RAM tier, model, engine base URL, input digest). Retune trigger
per DSpine: any change to hardware / model / workload digests the
profile as stale.
"""

from __future__ import annotations

import hashlib
import json
import logging
import platform
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "fusion-bench.sps/v1"


@dataclass
class SpsProfile:
    schema: str = SCHEMA_VERSION
    generated_at: str = ""
    model: str = ""
    backend: str = "mlx"
    chip: str = ""
    ram_gb: float = 0.0
    engine_base_url: str = ""
    engine_version: str = ""
    input_digest: str = ""
    width_transport: str = "request_body"
    engine_spec_support: str = "unverified"
    max_tokens: int = 128
    repeats: int = 3
    best: dict[str, int] = field(default_factory=dict)  # batch_size(str) -> width
    table: list[dict[str, Any]] = field(default_factory=list)
    acceptance_length: float | None = None
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info("SPS profile saved: %s", path)

    @classmethod
    def load(cls, path: str | Path) -> SpsProfile:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in raw.items() if k in known})


def current_hardware() -> tuple[str, float]:
    # Apple Silicon chip + RAM tier. sysctl is macOS-native, no extra deps.
    chip = ""
    ram_gb = 0.0
    try:
        chip = subprocess.run(
            ["sysctl", "-n", "machdep.cpu.brand_string"],
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
    except Exception as e:
        logger.warning("Failed to read chip model: %s", e)
    try:
        membytes = int(
            subprocess.run(
                ["sysctl", "-n", "hw.memsize"],
                capture_output=True,
                text=True,
                timeout=5,
            ).stdout.strip()
        )
        ram_gb = round(membytes / (1024.0**3), 1)
    except Exception as e:
        logger.warning("Failed to read RAM size: %s", e)
    if not chip:
        chip = platform.machine()
    return chip, ram_gb


def file_digest(path: str | Path) -> str:
    # sha256 of the prefix file bytes — any workload edit invalidates the profile.
    h = hashlib.sha256()
    h.update(Path(path).read_bytes())
    return h.hexdigest()[:16]


def is_stale(profile: SpsProfile, prefix_path: str | Path | None = None) -> list[str]:
    reasons: list[str] = []
    chip, ram_gb = current_hardware()
    if profile.chip and profile.chip != chip:
        reasons.append(f"hardware changed: profiled on {profile.chip}, now {chip}")
    if profile.ram_gb and profile.ram_gb != ram_gb:
        reasons.append(f"RAM changed: profiled at {profile.ram_gb}GB, now {ram_gb}GB")
    if prefix_path is not None and profile.input_digest:
        now = file_digest(prefix_path)
        if now != profile.input_digest:
            reasons.append(f"workload changed: digest {profile.input_digest} -> {now}")
    if profile.engine_spec_support == "unverified":
        reasons.append(
            "engine per-request speculative support unverified (upstream "
            "fusion-mlx#1528) — width axis may not have been applied"
        )
    if reasons:
        logger.warning("SPS profile stale (%d reasons)", len(reasons))
    else:
        logger.info("SPS profile fresh")
    return reasons
