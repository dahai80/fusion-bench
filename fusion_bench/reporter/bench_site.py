"""BenchSite reporter — formats Fusion-Bench results for bench.dpdns.org submission.

BenchSite schema:
- chip_name, memory_gb, gpu_cores, os_version
- model_name, quantization, context_length
- pp_tps (prefill), tg_tps (decode), ttft_ms, peak_memory_gb
- batching_results, owner_hash, submission_group
"""

from __future__ import annotations

import json
import platform
import subprocess
from dataclasses import dataclass, field
from typing import Any

from ..engine.benchmark import SpeedMetrics, BenchmarkResult


@dataclass
class BenchSiteEntry:
    """A single benchmark entry formatted for bench.dpdns.org submission."""

    chip_name: str = ""
    chip_variant: str = ""
    memory_gb: int = 0
    gpu_cores: int = 0
    os_version: str = ""
    omlx_version: str = "fusion-mlx"

    model_name: str = ""
    quantization: str = ""
    context_length: int = 4096

    pp_tps: float = 0.0
    tg_tps: float = 0.0
    ttft_ms: float | None = None
    peak_memory_gb: float | None = None

    batching_results: list[dict] | None = None
    owner_hash: str = ""
    submission_group: str = "fusion-bench"

    def to_dict(self) -> dict[str, Any]:
        """Convert to bench-site API format."""
        d = {
            "chip_name": self.chip_name,
            "chip_variant": self.chip_variant,
            "memory_gb": self.memory_gb,
            "gpu_cores": self.gpu_cores,
            "os_version": self.os_version,
            "omlx_version": self.omlx_version,
            "model_name": self.model_name,
            "quantization": self.quantization,
            "context_length": self.context_length,
            "pp_tps": self.pp_tps,
            "tg_tps": self.tg_tps,
            "submission_group": self.submission_group,
        }
        if self.ttft_ms is not None:
            d["ttft_ms"] = self.ttft_ms
        if self.peak_memory_gb is not None:
            d["peak_memory_gb"] = self.peak_memory_gb
        if self.batching_results:
            d["batching_results"] = self.batching_results
        if self.owner_hash:
            d["owner_hash"] = self.owner_hash
        return d


class BenchSiteReporter:
    """Converts Fusion-Bench results to bench.dpdns.org format."""

    @staticmethod
    def detect_hardware() -> dict[str, Any]:
        """Auto-detect hardware specs for the submission."""
        info = {}
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
                    info["chip_name"] = gpu.get("sppci_model", "").replace("Apple", "").strip()
                    info["chip_variant"] = ""
                    cores = gpu.get("sppci_cores", 0)
                    info["gpu_cores"] = int(cores) if cores else 0
        except Exception:
            pass

        try:
            import psutil
            info["memory_gb"] = round(psutil.virtual_memory().total / (1024**3))
        except ImportError:
            try:
                result = subprocess.run(
                    ["sysctl", "-n", "hw.memsize"],
                    capture_output=True, text=True, timeout=3,
                )
                if result.returncode == 0:
                    info["memory_gb"] = round(int(result.stdout.strip()) / (1024**3))
            except Exception:
                info["memory_gb"] = 0

        os_ver = platform.mac_ver()[0]
        info["os_version"] = f"macOS {os_ver}" if os_ver else ""

        if "chip_name" not in info:
            # Fallback: parse from platform
            proc = platform.processor() or "Apple Silicon"
            info["chip_name"] = proc.replace("Apple", "").strip() or "Apple Silicon"
            info["gpu_cores"] = info.get("gpu_cores", 0)
            info["memory_gb"] = info.get("memory_gb", 0)

        return info

    @staticmethod
    def from_speed_metrics(
        metrics: SpeedMetrics,
        model_name: str,
        quantization: str = "mxfp8",
        context_length: int = 4096,
        submission_group: str = "fusion-bench",
        owner_hash: str = "",
    ) -> BenchSiteEntry:
        """Convert SpeedMetrics to a BenchSiteEntry."""
        hw = BenchSiteReporter.detect_hardware()
        return BenchSiteEntry(
            chip_name=hw.get("chip_name", "Apple Silicon"),
            chip_variant=hw.get("chip_variant", ""),
            memory_gb=hw.get("memory_gb", 0),
            gpu_cores=hw.get("gpu_cores", 0),
            os_version=hw.get("os_version", ""),
            model_name=model_name,
            quantization=quantization,
            context_length=context_length,
            pp_tps=metrics.prefill_speed,
            tg_tps=metrics.decode_speed,
            ttft_ms=metrics.prefill_time * 1000 if metrics.prefill_time > 0 else None,
            peak_memory_gb=round(metrics.peak_memory_mb / 1024, 2) if metrics.peak_memory_mb > 0 else None,
            owner_hash=owner_hash,
            submission_group=submission_group,
        )

    @staticmethod
    def from_benchmark_result(
        result: BenchmarkResult,
        submission_group: str = "fusion-bench",
        owner_hash: str = "",
    ) -> BenchSiteEntry:
        """Convert a BenchmarkResult to a BenchSiteEntry."""
        # Extract quantization from model name (e.g., "qwen3.5-9b-mxfp4")
        model_parts = result.model.split("-")
        quant = "mxfp8"
        for part in model_parts:
            if any(q in part.lower() for q in ["mxfp", "quant", "mixed"]):
                quant = part
                break
        base_model = result.model.replace(f"-{quant}", "") if quant != "mxfp8" else result.model

        return BenchSiteReporter.from_speed_metrics(
            metrics=result.metrics,
            model_name=base_model,
            quantization=quant,
            context_length=result.config.get("max_tokens", 4096),
            submission_group=submission_group,
            owner_hash=owner_hash,
        )


class BenchSiteSubmitter:
    """Submits benchmark results to bench.dpdns.org API."""

    def __init__(self, api_url: str = "https://bench.dpdns.org/api/benchmarks"):
        self.api_url = api_url

    async def submit(self, entry: BenchSiteEntry) -> dict:
        """Submit a single benchmark entry to bench-site."""
        import httpx
        payload = entry.to_dict()
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(self.api_url, json=payload)
                if resp.status_code == 201:
                    data = resp.json()
                    return {"status": "created", "id": data.get("id"), "url": data.get("url")}
                elif resp.status_code == 409:
                    data = resp.json()
                    return {"status": "duplicate", "existing_id": data.get("existing_id"), "url": data.get("existing_url")}
                else:
                    return {"status": "error", "detail": resp.text}
        except Exception as e:
            return {"status": "error", "detail": str(e)}

    async def submit_batch(self, entries: list[BenchSiteEntry]) -> list[dict]:
        """Submit multiple benchmark entries."""
        results = []
        for entry in entries:
            result = await self.submit(entry)
            results.append(result)
            if result.get("status") == "created":
                print(f"  ✅ Submitted: {entry.model_name} ({entry.quantization}) → {result.get('url')}")
            elif result.get("status") == "duplicate":
                print(f"  ⏭️  Duplicate: {entry.model_name} ({entry.quantization}) → {result.get('url')}")
            else:
                print(f"  ❌ Failed: {entry.model_name} ({entry.quantization}): {result.get('detail')}")
        return results