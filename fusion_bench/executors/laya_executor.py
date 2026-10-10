"""Laya-MLX integration benchmark executor (#22, spec §五).

Benchmarks the laya-mlx decision endpoint (/v1/laya/decide) across 6 dimensions:
1. Decision latency — P50/P95/P99 for short/medium/long prompts × presets
2. Intent classification accuracy — 200-prompt test set vs ground truth
3. Guardrail precision/recall/F1 — 100-prompt safety test set per dimension
4. Tool selection success rate — 100-request test set vs expected tools
5. VRAM isolation — /stats check for laya model residency under load
6. End-to-end latency — full chat completion path (gateway → mlx → response)

When /v1/laya/decide returns 404 (upstream gateway #191 not landed), dims 1-4
auto-skip with a warning; dims 5-6 still execute against /stats and chat API.
"""

from __future__ import annotations

import json
import logging
import os
import statistics
import time
from pathlib import Path
from typing import Any

import httpx

from ..core.plugin_base import CaseResult, EvalResult, ExecutorPlugin, ExecutorType, TaskConfig

logger = logging.getLogger(__name__)

_DEFAULT_TESTSET_DIR = Path(__file__).resolve().parent.parent.parent / "benchmarks" / "testsets"

_PROMPT_LENGTHS = {
    "short": 50,
    "medium": 250,
    "long": 800,
}

_PRESETS = ["router", "guard", "moderation"]

_SPEC_TARGETS = {
    "latency_p50_ms": 15.0,
    "intent_accuracy": 0.80,
    "guardrail_precision": 0.90,
    "guardrail_recall": 0.85,
    "tool_success_rate": 0.999,
    "e2e_overhead_ms": 20.0,
}


class LayaBenchmarkExecutor(ExecutorPlugin):
    name = "laya"
    executor_type = ExecutorType.LAYA

    def __init__(self, mlx_base_url: str | None = None, api_key: str | None = None):
        self.mlx_base_url = (mlx_base_url or os.environ.get("FUSION_MLX_URL", "http://localhost:11432/v1")).rstrip("/")
        self.api_key = api_key or os.environ.get("FUSION_MLX_API_KEY", "local")
        self._laya_available: bool | None = None

    async def run(self, config: TaskConfig) -> EvalResult:
        start = time.time()
        model = config.model or ""
        testset_dir = Path(config.get("testset_dir", str(_DEFAULT_TESTSET_DIR)))
        laya_available = await self._check_laya_endpoint()
        dims: dict[str, Any] = {"laya_endpoint_available": laya_available}
        cases: list[CaseResult] = []
        errors: list[str] = []

        if not laya_available:
            logger.warning(
                "Laya endpoint /v1/laya/decide not available (404); dims 1-4 auto-skip. Upstream: fusion-gateway #191"
            )
            errors.append("laya endpoint not available (gateway #191 not landed); dims 1-4 skipped")

        # Dim 1: Decision latency
        if laya_available:
            lat = await self._bench_latency()
            dims["decision_latency"] = lat
        else:
            dims["decision_latency"] = {"skipped": True}

        # Dim 2: Intent classification accuracy
        intent_set = self._load_testset(testset_dir / "laya_intent_200.json")
        if laya_available and intent_set:
            intent_result = await self._bench_intent(intent_set)
            dims["intent_accuracy"] = intent_result
        else:
            dims["intent_accuracy"] = {"skipped": True, "testset_size": len(intent_set)}

        # Dim 3: Guardrail precision/recall
        guard_set = self._load_testset(testset_dir / "laya_guardrail_100.json")
        if laya_available and guard_set:
            guard_result = await self._bench_guardrail(guard_set)
            dims["guardrail"] = guard_result
        else:
            dims["guardrail"] = {"skipped": True, "testset_size": len(guard_set)}

        # Dim 4: Tool selection
        tool_set = self._load_testset(testset_dir / "laya_tools_100.json")
        if laya_available and tool_set:
            tool_result = await self._bench_tools(tool_set)
            dims["tool_selection"] = tool_result
        else:
            dims["tool_selection"] = {"skipped": True, "testset_size": len(tool_set)}

        # Dim 5: VRAM isolation (always runs — uses /stats)
        vram = await self._bench_vram()
        dims["vram_isolation"] = vram

        # Dim 6: E2E latency (needs a loaded model)
        if model:
            e2e = await self._bench_e2e(model)
            dims["e2e_latency"] = e2e
        else:
            dims["e2e_latency"] = {"skipped": True, "reason": "no model specified"}

        composite = self._composite_score(dims)
        report_dir = Path(config.get("report_dir", "benchmarks/results/laya-integration"))
        report_paths = self._write_report(dims, composite, report_dir, model)

        return EvalResult(
            task_id=config.task_id,
            executor_key=self.name,
            model=model,
            level="L4",
            metric_name="laya_composite",
            metric_value=round(composite, 4),
            cases=cases,
            duration_seconds=time.time() - start,
            errors=errors,
            meta={
                "dimensions": dims,
                "spec_targets": _SPEC_TARGETS,
                "report_files": report_paths,
                "testsets": {
                    "intent": len(intent_set),
                    "guardrail": len(guard_set),
                    "tools": len(tool_set),
                },
            },
        )

    async def _check_laya_endpoint(self) -> bool:
        if self._laya_available is not None:
            return self._laya_available
        try:
            async with httpx.AsyncClient(timeout=5.0, headers={"Authorization": f"Bearer {self.api_key}"}) as client:
                resp = await client.post(
                    f"{self.mlx_base_url}/laya/decide",
                    json={"prompt": "ping", "preset": "router"},
                )
            self._laya_available = resp.status_code != 404
            logger.info(
                "Laya endpoint check: %s (status=%d)",
                "available" if self._laya_available else "not available",
                resp.status_code,
            )
        except Exception as e:
            logger.debug("Laya endpoint check failed: %s", e)
            self._laya_available = False
        return self._laya_available

    async def _call_laya_decide(self, prompt: str, preset: str = "router") -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30.0, headers={"Authorization": f"Bearer {self.api_key}"}) as client:
            resp = await client.post(
                f"{self.mlx_base_url}/laya/decide",
                json={"prompt": prompt, "preset": preset},
            )
            resp.raise_for_status()
            return resp.json()

    async def _bench_latency(self) -> dict[str, Any]:
        results: dict[str, dict[str, float]] = {}
        all_latencies: list[float] = []
        for length_name, target_chars in _PROMPT_LENGTHS.items():
            prompt = " ".join(["word"] * (target_chars // 5 + 1))
            for preset in _PRESETS:
                latencies: list[float] = []
                for _ in range(10):
                    t0 = time.perf_counter()
                    try:
                        await self._call_laya_decide(prompt, preset)
                        latencies.append((time.perf_counter() - t0) * 1000)
                    except Exception as e:
                        logger.warning("latency bench failed (%s/%s): %s", length_name, preset, e)
                key = f"{length_name}_{preset}"
                if latencies:
                    results[key] = self._percentiles(latencies)
                    all_latencies.extend(latencies)
        overall = self._percentiles(all_latencies) if all_latencies else {"p50": 0, "p95": 0, "p99": 0}
        logger.info("Laya latency: p50=%.1fms p95=%.1fms p99=%.1fms", overall["p50"], overall["p95"], overall["p99"])
        return {"per_config": results, "overall": overall}

    async def _bench_intent(self, testset: list[dict]) -> dict[str, Any]:
        predictions: list[str] = []
        ground_truth: list[str] = []
        for item in testset:
            try:
                result = await self._call_laya_decide(item.get("prompt", ""), "router")
                pred = str(result.get("intent", "unknown"))
            except Exception as e:
                logger.debug("intent bench item failed: %s", e)
                pred = "unknown"
            predictions.append(pred)
            ground_truth.append(item.get("expected_intent", "unknown"))
        accuracy = sum(1 for p, g in zip(predictions, ground_truth, strict=False) if p == g) / max(len(ground_truth), 1)
        prf1 = self._compute_prf1(predictions, ground_truth)
        logger.info("Laya intent accuracy: %.1f%%", accuracy * 100)
        return {"accuracy": round(accuracy, 4), "per_class": prf1, "sample_count": len(testset)}

    async def _bench_guardrail(self, testset: list[dict]) -> dict[str, Any]:
        predictions: list[str] = []
        ground_truth: list[str] = []
        per_dim: dict[str, dict[str, int]] = {}
        for item in testset:
            try:
                result = await self._call_laya_decide(item.get("prompt", ""), "guard")
                score = float(result.get("safety_score", result.get("score", 0.5)))
                pred = "unsafe" if score >= 0.5 else "safe"
            except Exception as e:
                logger.debug("guardrail bench item failed: %s", e)
                pred = "safe"
            predictions.append(pred)
            gt = item.get("label", "safe")
            ground_truth.append(gt)
            dim = item.get("dimension", "unknown")
            if dim not in per_dim:
                per_dim[dim] = {"tp": 0, "fp": 0, "tn": 0, "fn": 0}
            if pred == "unsafe" and gt == "unsafe":
                per_dim[dim]["tp"] += 1
            elif pred == "unsafe" and gt == "safe":
                per_dim[dim]["fp"] += 1
            elif pred == "safe" and gt == "safe":
                per_dim[dim]["tn"] += 1
            else:
                per_dim[dim]["fn"] += 1
        overall_prf1 = self._compute_prf1(predictions, ground_truth)
        dim_prf1 = {d: self._prf1_from_counts(c) for d, c in per_dim.items()}
        logger.info(
            "Laya guardrail: precision=%.2f recall=%.2f",
            overall_prf1.get("precision", 0),
            overall_prf1.get("recall", 0),
        )
        return {"overall": overall_prf1, "per_dimension": dim_prf1, "sample_count": len(testset)}

    async def _bench_tools(self, testset: list[dict]) -> dict[str, Any]:
        correct = 0
        fallback = 0
        predictions: list[str] = []
        ground_truth: list[str] = []
        for item in testset:
            try:
                result = await self._call_laya_decide(item.get("request", ""), "moderation")
                pred = str(result.get("tool", result.get("choice", "fallback")))
            except Exception as e:
                logger.debug("tool bench item failed: %s", e)
                pred = "fallback"
            if pred == "fallback":
                fallback += 1
            predictions.append(pred)
            gt = item.get("expected_tool", "")
            ground_truth.append(gt)
            if pred == gt:
                correct += 1
        accuracy = correct / max(len(testset), 1)
        fallback_rate = fallback / max(len(testset), 1)
        logger.info("Laya tool selection: accuracy=%.1f%% fallback=%.1f%%", accuracy * 100, fallback_rate * 100)
        return {"accuracy": round(accuracy, 4), "fallback_rate": round(fallback_rate, 4), "sample_count": len(testset)}

    async def _bench_vram(self) -> dict[str, Any]:
        stats: dict[str, Any] = {"peak_memory_mb": 0.0, "models_loaded": 0, "laya_resident": False, "stable": False}
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.mlx_base_url}/stats")
                if resp.status_code != 200:
                    logger.debug("VRAM /stats returned %d", resp.status_code)
                    return stats
                data = resp.json()
            mem_str = str(data.get("model_memory_used_formatted", data.get("model_memory_used", "0B")))
            models = data.get("models_loaded", [])
            stats["peak_memory_mb"] = self._parse_memory_mb(mem_str)
            stats["models_loaded"] = len(models) if isinstance(models, list) else models
            stats["laya_resident"] = any("laya" in str(m).lower() for m in (models if isinstance(models, list) else []))
            stats["stable"] = stats["peak_memory_mb"] > 0
            logger.info(
                "VRAM: peak=%.1fMB laya_resident=%s models=%s",
                stats["peak_memory_mb"],
                stats["laya_resident"],
                stats["models_loaded"],
            )
        except Exception as e:
            logger.debug("VRAM stats unavailable: %s", e)
        return stats

    async def _bench_e2e(self, model: str) -> dict[str, Any]:
        ttft_ms = 0.0
        total_ms = 0.0
        try:
            t0 = time.perf_counter()
            async with (
                httpx.AsyncClient(timeout=60.0, headers={"Authorization": f"Bearer {self.api_key}"}) as client,
                client.stream(
                    "POST",
                    f"{self.mlx_base_url}/chat/completions",
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": "hello"}],
                        "max_tokens": 16,
                        "stream": True,
                    },
                ) as resp,
            ):
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[6:].strip()
                    if data == "[DONE]":
                        break
                    if ttft_ms == 0.0:
                        ttft_ms = (time.perf_counter() - t0) * 1000
            total_ms = (time.perf_counter() - t0) * 1000
            logger.info("E2E: ttft=%.1fms total=%.1fms", ttft_ms, total_ms)
        except Exception as e:
            logger.warning("E2E benchmark failed: %s", e)
            return {"ttft_ms": 0.0, "total_ms": 0.0, "overhead_ms": 0.0, "error": str(e)}
        overhead = max(total_ms - ttft_ms, 0.0)
        return {"ttft_ms": round(ttft_ms, 2), "total_ms": round(total_ms, 2), "overhead_ms": round(overhead, 2)}

    @staticmethod
    def _percentiles(latencies: list[float]) -> dict[str, float]:
        if not latencies:
            return {"p50": 0.0, "p95": 0.0, "p99": 0.0}
        s = sorted(latencies)
        n = len(s)
        p50 = s[n // 2] if n % 2 == 1 else statistics.mean(s[n // 2 - 1 : n // 2 + 1])
        p95 = s[min(int(n * 0.95), n - 1)]
        p99 = s[min(int(n * 0.99), n - 1)]
        return {"p50": round(p50, 2), "p95": round(p95, 2), "p99": round(p99, 2)}

    @staticmethod
    def _compute_prf1(predictions: list[str], ground_truth: list[str]) -> dict[str, Any]:
        labels = sorted(set(ground_truth) | set(predictions))
        per_class: dict[str, dict[str, float]] = {}
        for label in labels:
            tp = sum(1 for p, g in zip(predictions, ground_truth, strict=False) if p == label and g == label)
            fp = sum(1 for p, g in zip(predictions, ground_truth, strict=False) if p == label and g != label)
            fn = sum(1 for p, g in zip(predictions, ground_truth, strict=False) if p != label and g == label)
            precision = tp / max(tp + fp, 1)
            recall = tp / max(tp + fn, 1)
            f1 = 2 * precision * recall / max(precision + recall, 1e-9)
            per_class[label] = {
                "precision": round(precision, 4),
                "recall": round(recall, 4),
                "f1": round(f1, 4),
                "support": tp + fn,
            }
        macro_p = statistics.mean([v["precision"] for v in per_class.values()]) if per_class else 0.0
        macro_r = statistics.mean([v["recall"] for v in per_class.values()]) if per_class else 0.0
        macro_f1 = statistics.mean([v["f1"] for v in per_class.values()]) if per_class else 0.0
        return {
            "per_class": per_class,
            "macro_precision": round(macro_p, 4),
            "macro_recall": round(macro_r, 4),
            "macro_f1": round(macro_f1, 4),
        }

    @staticmethod
    def _prf1_from_counts(counts: dict[str, int]) -> dict[str, float]:
        tp, fp, tn, fn = counts.get("tp", 0), counts.get("fp", 0), counts.get("tn", 0), counts.get("fn", 0)
        precision = tp / max(tp + fp, 1)
        recall = tp / max(tp + fn, 1)
        f1 = 2 * precision * recall / max(precision + recall, 1e-9)
        return {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "tp": tp,
            "fp": fp,
            "tn": tn,
            "fn": fn,
        }

    @staticmethod
    def _parse_memory_mb(mem_str: str) -> float:
        if not mem_str:
            return 0.0
        s = mem_str.strip().upper()
        try:
            if s.endswith("GB"):
                return float(s[:-2].strip()) * 1024
            if s.endswith("MB"):
                return float(s[:-2].strip())
            if s.endswith("KB"):
                return float(s[:-2].strip()) / 1024
            return float(s)
        except ValueError:
            return 0.0

    def _composite_score(self, dims: dict[str, Any]) -> float:
        lat = dims.get("decision_latency", {})
        lat_score = (
            1.0
            if lat.get("skipped")
            else min(lat.get("overall", {}).get("p50", 999) / _SPEC_TARGETS["latency_p50_ms"], 1.0)
        )
        if lat.get("skipped"):
            lat_score = 0.0
        intent = dims.get("intent_accuracy", {})
        intent_score = (
            0.0 if intent.get("skipped") else min(intent.get("accuracy", 0) / _SPEC_TARGETS["intent_accuracy"], 1.0)
        )
        guard = dims.get("guardrail", {})
        guard_score = (
            0.0
            if guard.get("skipped")
            else min(guard.get("overall", {}).get("macro_precision", 0) / _SPEC_TARGETS["guardrail_precision"], 1.0)
        )
        tools = dims.get("tool_selection", {})
        tool_score = (
            0.0 if tools.get("skipped") else min(tools.get("accuracy", 0) / _SPEC_TARGETS["tool_success_rate"], 1.0)
        )
        vram = dims.get("vram_isolation", {})
        vram_score = 1.0 if vram.get("laya_resident") or vram.get("stable") else 0.0
        e2e = dims.get("e2e_latency", {})
        if e2e.get("skipped"):
            e2e_score = 0.0
        else:
            e2e_score = (
                1.0
                if e2e.get("overhead_ms", 999) <= _SPEC_TARGETS["e2e_overhead_ms"]
                else min(e2e.get("overhead_ms", 999) / _SPEC_TARGETS["e2e_overhead_ms"], 1.0)
            )
        weights = {"latency": 0.25, "intent": 0.25, "guardrail": 0.20, "tools": 0.15, "vram": 0.05, "e2e": 0.10}
        active = sum(
            w
            for k, w in weights.items()
            if not dims.get(
                {
                    "latency": "decision_latency",
                    "intent": "intent_accuracy",
                    "guardrail": "guardrail",
                    "tools": "tool_selection",
                    "vram": "vram_isolation",
                    "e2e": "e2e_latency",
                }[k],
                {},
            ).get("skipped")
        )
        if active == 0:
            return 0.0
        raw = (
            weights["latency"] * lat_score
            + weights["intent"] * intent_score
            + weights["guardrail"] * guard_score
            + weights["tools"] * tool_score
            + weights["vram"] * vram_score
            + weights["e2e"] * e2e_score
        )
        return raw / active if active < sum(weights.values()) else raw

    @staticmethod
    def _load_testset(path: Path) -> list[dict]:
        if not path.exists():
            logger.warning("Testset not found: %s", path)
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception as e:
            logger.warning("Failed to load testset %s: %s", path, e)
            return []

    def _write_report(self, dims: dict[str, Any], composite: float, report_dir: Path, model: str) -> dict[str, str]:
        report_dir.mkdir(parents=True, exist_ok=True)
        report = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "model": model,
            "endpoint": f"{self.mlx_base_url}/laya/decide",
            "laya_available": dims.get("laya_endpoint_available", False),
            "composite_score": round(composite, 4),
            "dimensions": dims,
            "spec_targets": _SPEC_TARGETS,
        }
        json_path = report_dir / "report.json"
        json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        md_path = report_dir / "report.md"
        md_path.write_text(self._render_markdown_report(report), encoding="utf-8")
        logger.info("Laya benchmark report written to %s", report_dir)
        return {"json": str(json_path), "markdown": str(md_path)}

    @staticmethod
    def _render_markdown_report(report: dict[str, Any]) -> str:
        dims = report.get("dimensions", {})
        targets = report.get("spec_targets", {})
        lines = [
            "# Laya-MLX Integration Benchmark Report",
            "",
            f"**Timestamp**: {report.get('timestamp', 'N/A')}",
            f"**Model**: {report.get('model', 'N/A')}",
            f"**Endpoint**: {report.get('endpoint', 'N/A')}",
            f"**Laya Available**: {'✅ Yes' if report.get('laya_available') else '❌ No (upstream gateway #191 not landed)'}",
            f"**Composite Score**: {report.get('composite_score', 0):.4f}",
            "",
            "## Spec Target Comparison",
            "",
            "| Dimension | Metric | Spec Target | Actual | Status |",
            "|-----------|--------|-------------|--------|--------|",
        ]
        lat = dims.get("decision_latency", {})
        if lat.get("skipped"):
            lines.append("| Decision Latency | P50 (ms) | < 15 | — | ⏭️ Skipped |")
        else:
            p50 = lat.get("overall", {}).get("p50", 0)
            lines.append(
                f"| Decision Latency | P50 (ms) | < {targets.get('latency_p50_ms', 15)} | {p50} | {'✅' if p50 < targets.get('latency_p50_ms', 15) else '❌'} |"
            )
        intent = dims.get("intent_accuracy", {})
        if intent.get("skipped"):
            lines.append("| Intent Accuracy | accuracy | > 80% | — | ⏭️ Skipped |")
        else:
            acc = intent.get("accuracy", 0)
            lines.append(
                f"| Intent Accuracy | accuracy | > {targets.get('intent_accuracy', 0.8) * 100:.0f}% | {acc * 100:.1f}% | {'✅' if acc >= targets.get('intent_accuracy', 0.8) else '❌'} |"
            )
        guard = dims.get("guardrail", {})
        if guard.get("skipped"):
            lines.append("| Guardrail | precision | > 90% | — | ⏭️ Skipped |")
        else:
            p = guard.get("overall", {}).get("macro_precision", 0)
            lines.append(
                f"| Guardrail | precision | > {targets.get('guardrail_precision', 0.9) * 100:.0f}% | {p * 100:.1f}% | {'✅' if p >= targets.get('guardrail_precision', 0.9) else '❌'} |"
            )
        tools = dims.get("tool_selection", {})
        if tools.get("skipped"):
            lines.append("| Tool Selection | accuracy | ≥ 99.9% | — | ⏭️ Skipped |")
        else:
            acc = tools.get("accuracy", 0)
            lines.append(
                f"| Tool Selection | accuracy | ≥ {targets.get('tool_success_rate', 0.999) * 100:.1f}% | {acc * 100:.1f}% | {'✅' if acc >= targets.get('tool_success_rate', 0.999) else '❌'} |"
            )
        e2e = dims.get("e2e_latency", {})
        if e2e.get("skipped"):
            lines.append("| E2E Latency | overhead (ms) | < 20 | — | ⏭️ Skipped |")
        else:
            oh = e2e.get("overhead_ms", 0)
            lines.append(
                f"| E2E Latency | overhead (ms) | < {targets.get('e2e_overhead_ms', 20)} | {oh} | {'✅' if oh < targets.get('e2e_overhead_ms', 20) else '❌'} |"
            )
        vram = dims.get("vram_isolation", {})
        lines.append(
            f"| VRAM Isolation | laya resident | yes | {vram.get('laya_resident', False)} | {'✅' if vram.get('laya_resident') else '❌'} |"
        )
        lines.append("")
        lines.append("## Test Sets")
        lines.append("")
        ts = report.get("dimensions", {}).get("testsets", report.get("testsets", {}))
        if ts:
            lines.append(f"- Intent classification: {ts.get('intent', 0)} prompts")
            lines.append(f"- Guardrail: {ts.get('guardrail', 0)} prompts")
            lines.append(f"- Tool selection: {ts.get('tools', 0)} requests")
        lines.append("")
        lines.append("## Notes")
        lines.append("")
        lines.append("- Upstream dependency: fusion-gateway #191 (LayaClassifier implementing IntentClassifier)")
        lines.append("- When endpoint is 404, dimensions 1-4 auto-skip; dimensions 5-6 still execute")
        lines.append("- Test sets committed to `benchmarks/testsets/` for reproducibility")
        return "\n".join(lines)

    def is_available(self) -> bool:
        return True
