"""Metal Monitor — collects real GPU performance metrics from Apple Silicon.

Uses system_profiler, sysctl, and fusion-mlx stats to gather GPU metrics.
No direct MLX imports — all data comes from system commands or HTTP API.
"""

from __future__ import annotations

import json
import logging
import subprocess
from typing import Any

logger = logging.getLogger(__name__)


class MetalMonitor:
    """Apple Metal performance monitor.

    Collects GPU model, core count, memory usage, and MLX runtime stats
    through system_profiler and fusion-mlx HTTP API.
    """

    @staticmethod
    def collect_gpu_info() -> dict[str, Any]:
        """Collect GPU hardware information via system_profiler."""
        try:
            result = subprocess.run(
                ["system_profiler", "SPDisplaysDataType", "-json"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode != 0:
                return {}
            data = json.loads(result.stdout)
            displays = data.get("SPDisplaysDataType", [])
            if not displays:
                return {}
            gpu = displays[0]
            return {
                "gpu_model": gpu.get("sppci_model", "Unknown"),
                "gpu_cores": gpu.get("sppci_cores", 0),
                "metal_family": gpu.get("metal_family", ""),
                "vram": gpu.get("spdisplays_vram", "Unknown"),
                "chip_type": gpu.get("sppci_device_type", ""),
            }
        except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError) as e:
            logger.debug("Failed to collect GPU info: %s", e)
            return {}

    @staticmethod
    def collect_system_info() -> dict[str, Any]:
        """Collect system info via sysctl."""
        info = {}
        try:
            result = subprocess.run(
                ["sysctl", "-n", "hw.memsize", "hw.ncpu", "machdep.cpu.brand_string"],
                capture_output=True, text=True, timeout=3,
            )
            if result.returncode == 0:
                lines = result.stdout.strip().split("\n")
                if len(lines) >= 1:
                    info["total_memory_gb"] = round(int(lines[0]) / (1024**3), 1)
                if len(lines) >= 2:
                    info["cpu_cores"] = int(lines[1])
                if len(lines) >= 3:
                    info["cpu_model"] = lines[2]
        except (subprocess.TimeoutExpired, FileNotFoundError, ValueError) as e:
            logger.debug("Failed to collect system info: %s", e)
        return info

    @staticmethod
    async def collect_mlx_stats(mlx_url: str = "http://localhost:11434") -> dict[str, Any]:
        """Collect MLX runtime stats from fusion-mlx."""
        import httpx
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(f"{mlx_url}/stats")
                if resp.status_code == 200:
                    data = resp.json()
                    return {
                        "models_loaded": data.get("models_loaded", 0),
                        "total_requests": data.get("total_requests", 0),
                        "model_memory_used": data.get("model_memory_used_formatted", "0B"),
                        "model_memory_max": data.get("model_memory_max_formatted", "unlimited"),
                        "total_prompt_tokens": data.get("total_prompt_tokens", 0),
                        "total_completion_tokens": data.get("total_tokens_generated", 0),
                    }
        except Exception as e:
            logger.debug("Failed to collect MLX stats: %s", e)
        return {}

    @staticmethod
    def collect_power_info() -> dict[str, Any]:
        """Collect power/thermal info via powermetrics (requires sudo)."""
        try:
            result = subprocess.run(
                ["pmset", "-g", "stats"],
                capture_output=True, text=True, timeout=3,
            )
            if result.returncode == 0:
                return {"power_stats": result.stdout[:500]}
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return {}

    async def collect_all(self, mlx_url: str = "http://localhost:11434") -> dict[str, Any]:
        """Collect all metrics in one call."""
        import asyncio
        gpu = self.collect_gpu_info()
        sys_info = self.collect_system_info()
        mlx = await self.collect_mlx_stats(mlx_url)
        power = self.collect_power_info()
        return {
            "gpu": gpu,
            "system": sys_info,
            "mlx": mlx,
            "power": power,
        }

    @staticmethod
    def format_report(data: dict[str, Any]) -> str:
        """Format collected metrics as a readable report."""
        lines = ["=== Metal Performance Report ===", ""]
        gpu = data.get("gpu", {})
        if gpu:
            lines.append(f"GPU Model: {gpu.get('gpu_model', 'N/A')}")
            lines.append(f"GPU Cores: {gpu.get('gpu_cores', 'N/A')}")
            lines.append(f"Metal Family: {gpu.get('metal_family', 'N/A')}")
            lines.append(f"VRAM: {gpu.get('vram', 'N/A')}")
            lines.append("")
        sys_info = data.get("system", {})
        if sys_info:
            lines.append(f"Total Memory: {sys_info.get('total_memory_gb', 'N/A')} GB")
            lines.append(f"CPU Cores: {sys_info.get('cpu_cores', 'N/A')}")
            lines.append(f"CPU Model: {sys_info.get('cpu_model', 'N/A')}")
            lines.append("")
        mlx = data.get("mlx", {})
        if mlx:
            lines.append(f"Models Loaded: {mlx.get('models_loaded', 0)}")
            lines.append(f"Total Requests: {mlx.get('total_requests', 0)}")
            lines.append(f"Memory Used: {mlx.get('model_memory_used', '0B')}")
            lines.append(f"Memory Max: {mlx.get('model_memory_max', 'unlimited')}")
        return "\n".join(lines)