"""GPU utilization monitor - real-time GPU usage tracking.

Importers/callers: api/app.py /system/gpu endpoint; engine/metal_monitor.py can use this.
Affected API: adds /system/gpu GET endpoint; no schema changes.
Data schema: GPUStats dataclass (utilization_pct, memory_used_gb, memory_total_gb, temperature_c, gpu_type, timestamp).
User instruction: "把所有没完全做完，没启动做，有差距的全部启动补齐" (Enhancement F real-time GPU monitoring).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)


@dataclass
class GPUStats:
    utilization_pct: float = 0.0
    memory_used_gb: float = 0.0
    memory_total_gb: float = 0.0
    temperature_c: float = 0.0
    gpu_type: str = "Apple Silicon"
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "utilization_pct": self.utilization_pct,
            "memory_used_gb": self.memory_used_gb,
            "memory_total_gb": self.memory_total_gb,
            "temperature_c": self.temperature_c,
            "gpu_type": self.gpu_type,
            "timestamp": self.timestamp or time.strftime("%Y-%m-%dT%H:%M:%S"),
        }


async def get_gpu_stats(base_url: str = "http://localhost:11434/v1") -> GPUStats:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{base_url.rstrip('/')}/stats")
            if resp.status_code == 200:
                data = resp.json()
                memory = data.get("memory", {})
                gpu = data.get("gpu", data.get("metal", {}))
                return GPUStats(
                    utilization_pct=gpu.get("utilization_pct", gpu.get("gpu_utilization", 0.0)),
                    memory_used_gb=memory.get("used_gb", gpu.get("memory_used_gb", 0.0)),
                    memory_total_gb=memory.get("total_gb", gpu.get("memory_total_gb", 0.0)),
                    temperature_c=gpu.get("temperature_c", 0.0),
                    gpu_type=gpu.get("type", "Apple Silicon"),
                )
    except Exception as e:
        logger.debug("GPU stats fetch failed: %s", e)

    stats = GPUStats()
    try:
        proc = await asyncio.create_subprocess_exec(
            "system_profiler",
            "SPDisplaysDataType",
            "-json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5.0)
        if proc.returncode == 0 and stdout:
            data = json.loads(stdout.decode())
            displays = data.get("SPDisplaysDataType", [])
            if displays:
                chip = displays[0].get("sppci_model", "Apple Silicon")
                stats.gpu_type = chip
                vram = displays[0].get("spdisplays_vram", "")
                if vram and "GB" in str(vram):
                    with contextlib.suppress(ValueError):
                        stats.memory_total_gb = float(str(vram).replace(" GB", ""))
    except Exception:
        pass

    return stats
