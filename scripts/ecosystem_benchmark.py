"""Ecosystem benchmark — fusion-mlx / fusion-code / fusion-security.
Importers/callers: developer running `python scripts/ecosystem_benchmark.py`.
Affected API: fusion-mlx /v1/*, bench-site /api/benchmarks.
Data schemas: BenchSiteRecord (chip_name, model_name, pp_tps, tg_tps, …).
User instruction: "fusion-bench能力均已经具备是不是对~/fusion/fusion-code的软件能力，
~/claude-home/fusion-mlx，~/fusion-security能力首先出一个benchmark评测，上传到bench.dpdns.org"
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fusion_bench.engine.benchmark import BenchmarkRunner
from fusion_bench.reporter.bench_site_db import BenchSiteDB

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

MLX_API_KEY = "dahai168"
MLX_BASE_URL = "http://localhost:11432/v1"

SPEED_MODELS = [
    "Qwen3-0.6B-4bit",
    "mlx-community--Llama-3.2-1B-Instruct-4bit",
    "mlx-community--Qwen3-4B-bf16",
    "Qwen3.5-9B-4bit",
    "Qwen3.6-27B-mxfp8",
    "DeepSeek-V4-Flash",
    "mlx-community--Qwen2.5-Coder-32B-Instruct-4bit",
]

CODE_PROMPTS = [
    {
        "name": "hello_world",
        "lang": "python",
        "prompt": "Write a Python function that returns 'Hello, World!'",
        "check": lambda c: "hello" in c.lower() and "def " in c,
    },
    {
        "name": "fibonacci",
        "lang": "python",
        "prompt": "Write a Python function fibonacci(n) that returns the n-th Fibonacci number.",
        "check": lambda c: "fib" in c.lower() and "def " in c,
    },
    {
        "name": "binary_search",
        "lang": "python",
        "prompt": "Write a Python function binary_search(arr, target) that returns the index of target in sorted array arr, or -1 if not found.",
        "check": lambda c: "binary" in c.lower() and "def " in c and "return" in c,
    },
    {
        "name": "quicksort",
        "lang": "python",
        "prompt": "Write a Python function quicksort(arr) that returns a sorted list using the quicksort algorithm.",
        "check": lambda c: "quick" in c.lower() and "def " in c,
    },
    {
        "name": "json_parser",
        "lang": "typescript",
        "prompt": "Write a TypeScript function parseSafe(jsonStr: string): unknown that safely parses JSON and returns null on error.",
        "check": lambda c: "parse" in c.lower() and ("function" in c or "=>" in c),
    },
]


async def phase1_speed():
    logger.info("=" * 60)
    logger.info("Phase 1: fusion-mlx Speed Benchmark")
    logger.info("=" * 60)
    runner = BenchmarkRunner(mlx_base_url=MLX_BASE_URL, api_key=MLX_API_KEY)
    db = BenchSiteDB()
    results = []
    for model in SPEED_MODELS:
        logger.info("Benchmarking %s ...", model)
        try:
            bench_results = await runner.benchmark(model, runs=3)
            for r in bench_results:
                rid = db.insert_from_benchmark(r)
                logger.info(
                    "  %s: decode=%.1f tok/s, prefill=%.1f tok/s, memory=%.0f MB [id=%d]",
                    r.model,
                    r.metrics.decode_speed,
                    r.metrics.prefill_speed,
                    r.metrics.peak_memory_mb,
                    rid,
                )
                results.append(r)
        except Exception as e:
            logger.error("  FAILED %s: %s", model, e)
    await runner.close()
    logger.info("Phase 1 complete: %d results uploaded", len(results))
    return results


async def phase2_security():
    logger.info("=" * 60)
    logger.info("Phase 2: fusion-mlx Security Probes")
    logger.info("=" * 60)
    db = BenchSiteDB()
    security_models = ["Qwen3.5-9B-4bit", "Qwen3.6-27B-mxfp8", "mlx-community--Qwen2.5-Coder-32B-Instruct-4bit"]
    probe_sets = ["injection", "harmful", "pii"]
    results = []
    for model in security_models:
        for probe_set in probe_sets:
            logger.info("Probing %s / %s ...", model, probe_set)
            try:
                from fusion_bench.core.plugin_base import TaskConfig
                from fusion_bench.executors.security_executor import SecurityExecutor

                executor = SecurityExecutor(mlx_base_url=MLX_BASE_URL, api_key=MLX_API_KEY)
                config = TaskConfig(
                    model=model,
                    task_id=f"security-{probe_set}",
                    executor_key="security",
                    params={"probe_set": probe_set, "max_probes": 5},
                )
                eval_result = await executor.run(config)
                rid = db.insert_from_eval_result(eval_result, model_name=model)
                logger.info(
                    "  %s/%s: safety_rate=%.2f, safe=%d/%d [id=%d]",
                    model,
                    probe_set,
                    eval_result.metric_value,
                    eval_result.meta.get("safe_count", 0) if eval_result.meta else 0,
                    eval_result.meta.get("total_probes", 0) if eval_result.meta else 0,
                    rid,
                )
                results.append(eval_result)
            except Exception as e:
                logger.error("  FAILED %s/%s: %s", model, probe_set, e)
    logger.info("Phase 2 complete: %d results uploaded", len(results))
    return results


async def phase3_code():
    logger.info("=" * 60)
    logger.info("Phase 3: fusion-code Code Generation Benchmark")
    logger.info("=" * 60)
    db = BenchSiteDB()
    import httpx

    code_model = "mlx-community--Qwen2.5-Coder-32B-Instruct-4bit"
    results = []
    async with httpx.AsyncClient(
        base_url=MLX_BASE_URL,
        timeout=120.0,
        headers={"Authorization": f"Bearer {MLX_API_KEY}"},
    ) as client:
        for task in CODE_PROMPTS:
            logger.info("Code task: %s (%s) ...", task["name"], task["lang"])
            t0 = time.perf_counter()
            try:
                resp = await client.post(
                    "/chat/completions",
                    json={
                        "model": code_model,
                        "messages": [{"role": "user", "content": task["prompt"]}],
                        "max_tokens": 512,
                        "temperature": 0.2,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                elapsed = time.perf_counter() - t0
                passed = task["check"](content)
                usage = data.get("usage", {})
                comp_tokens = usage.get("completion_tokens", 0)
                speed = comp_tokens / elapsed if elapsed > 0 else 0
                logger.info(
                    "  %s: passed=%s, tokens=%d, speed=%.1f tok/s, ttft=%.2fs",
                    task["name"],
                    passed,
                    comp_tokens,
                    speed,
                    elapsed,
                )
                hw_info = db._detect_hardware()
                record_dict = {
                    "chip_name": hw_info.get("chip_name", "Apple Silicon"),
                    "chip_variant": hw_info.get("chip_variant", ""),
                    "memory_gb": hw_info.get("memory_gb", 0),
                    "gpu_cores": hw_info.get("gpu_cores", 0),
                    "os_version": hw_info.get("os_version", ""),
                    "model_name": code_model,
                    "quantization": "4bit",
                    "context_length": 4096,
                    "pp_tps": 0.0,
                    "tg_tps": round(speed, 2),
                    "ttft_ms": round(elapsed * 1000, 2),
                    "peak_memory_gb": None,
                    "owner_hash": "",
                    "benchmark_type": "code",
                    "metric_name": task["name"],
                    "metric_value": 1.0 if passed else 0.0,
                    "detail": json.dumps(
                        {
                            "task": task["name"],
                            "lang": task["lang"],
                            "passed": passed,
                            "completion_tokens": comp_tokens,
                            "speed_tok_s": round(speed, 2),
                            "elapsed_s": round(elapsed, 2),
                            "prompt_tokens": usage.get("prompt_tokens", 0),
                        },
                        ensure_ascii=False,
                    ),
                }
                from fusion_bench.reporter.bench_site_db import BenchSiteRecord

                record = BenchSiteRecord(**record_dict)
                rid = db.insert(record)
                logger.info("  uploaded [id=%d]", rid)
                results.append(record_dict)
            except Exception as e:
                logger.error("  FAILED %s: %s", task["name"], e)
    logger.info("Phase 3 complete: %d results uploaded", len(results))
    return results


async def phase4_security_scan():
    logger.info("=" * 60)
    logger.info("Phase 4: fusion-security Scan Benchmark")
    logger.info("=" * 60)
    db = BenchSiteDB()
    scan_target = str(Path(__file__).resolve().parent.parent)
    results = []
    try:
        import subprocess

        venv_bin = str(Path(__file__).resolve().parent.parent / ".venv" / "bin")
        cli_path = str(Path(venv_bin) / "fusion-security")

        t0 = time.perf_counter()
        proc = subprocess.run(
            [cli_path, "scan", scan_target, "--format", "json", "--no-ai"],
            capture_output=True,
            text=True,
            timeout=300,
            env={**__import__("os").environ, "PATH": venv_bin + ":" + __import__("os").environ.get("PATH", "")},
        )
        elapsed = time.perf_counter() - t0
        scan_output = proc.stdout
        findings_count = 0
        severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
        try:
            scan_data = json.loads(scan_output)
            if isinstance(scan_data, list):
                findings_count = len(scan_data)
                for f in scan_data:
                    sev = f.get("severity", "info").lower()
                    if sev in severity_counts:
                        severity_counts[sev] += 1
            elif isinstance(scan_data, dict):
                findings_count = scan_data.get("total_findings", scan_data.get("findings_count", 0))
        except json.JSONDecodeError:
            findings_count = scan_output.count("finding") if scan_output else 0

        hw_info = db._detect_hardware()
        record_dict = {
            "chip_name": hw_info.get("chip_name", "Apple Silicon"),
            "chip_variant": hw_info.get("chip_variant", ""),
            "memory_gb": hw_info.get("memory_gb", 0),
            "gpu_cores": hw_info.get("gpu_cores", 0),
            "os_version": hw_info.get("os_version", ""),
            "model_name": "fusion-security",
            "quantization": "n/a",
            "context_length": 0,
            "pp_tps": 0.0,
            "tg_tps": 0.0,
            "ttft_ms": round(elapsed * 1000, 2),
            "peak_memory_gb": None,
            "owner_hash": "",
            "benchmark_type": "security_scan",
            "task_name": "code-scan",
            "metric_name": "findings_count",
            "metric_value": float(findings_count),
            "detail": json.dumps(
                {
                    "target": scan_target,
                    "findings_count": findings_count,
                    "severity_counts": severity_counts,
                    "elapsed_s": round(elapsed, 2),
                    "exit_code": proc.returncode,
                },
                ensure_ascii=False,
            ),
        }
        from fusion_bench.reporter.bench_site_db import BenchSiteRecord

        record = BenchSiteRecord(**record_dict)
        rid = db.insert(record)
        logger.info(
            "Scan complete: %d findings in %.1fs, exit=%d [id=%d]",
            findings_count,
            elapsed,
            proc.returncode,
            rid,
        )
        results.append(record_dict)
    except FileNotFoundError:
        logger.warning("fusion-security CLI not found, skipping scan benchmark")
    except Exception as e:
        logger.error("Scan FAILED: %s", e)
    logger.info("Phase 4 complete: %d results uploaded", len(results))
    return results


async def main():
    logger.info("Fusion Ecosystem Benchmark — started")
    logger.info("bench-site DB: %s", BenchSiteDB().stats())

    r1 = await phase1_speed()
    r2 = await phase2_security()
    r3 = await phase3_code()
    r4 = await phase4_security_scan()

    total = len(r1) + len(r2) + len(r3) + len(r4)
    logger.info("=" * 60)
    logger.info("ALL PHASES COMPLETE — %d total results uploaded", total)
    logger.info("  Phase 1 (speed):     %d", len(r1))
    logger.info("  Phase 2 (security):  %d", len(r2))
    logger.info("  Phase 3 (code):      %d", len(r3))
    logger.info("  Phase 4 (sec_scan):  %d", len(r4))
    logger.info("View results at https://bench.dpdns.org")
    final_stats = BenchSiteDB().stats()
    logger.info("bench-site DB final: %s", final_stats)


if __name__ == "__main__":
    asyncio.run(main())
