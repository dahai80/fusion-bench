"""BNUP 4-dimension evaluation executor (#17, spec §378-407).

Dimensions:
1. Format & Constraint — DSLFormatChecker.run_all (tag/json/schema/eval)
2. Math Reasoning — DSLEvalExecutor final_value vs ground_truth + unit + milestone
3. Socratic Quality — SxSJudge.judge_pair vs reference output (1-5)
4. System Performance — streaming TTFT + TPS (tokens/s)

Orchestrates checkers + judge over model output fetched from fusion-mlx.
No eval()/exec() on model output (delegates to AST-based DSLEvalExecutor).
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

import httpx

from ..checkers.dsl_eval_executor import DSLEvalExecutor
from ..checkers.dsl_format_checker import DSLFormatChecker, FormatReport
from ..core.plugin_base import CaseResult, EvalResult, ExecutorPlugin, ExecutorType, TaskConfig
from ..judge.sxs_config import SxSConfig, SxSVerdict, aggregate_verdicts
from ..judge.sxs_judge import SxSJudge

logger = logging.getLogger(__name__)

_GROUND_TRUTH_TOL = 1e-3


class BNUPEvaluator(ExecutorPlugin):
    name = "bnup"
    executor_type = ExecutorType.BNUP

    def __init__(
        self,
        mlx_base_url: str | None = None,
        format_checker: DSLFormatChecker | None = None,
        eval_executor: DSLEvalExecutor | None = None,
        sxs_judge: SxSJudge | None = None,
    ):
        self.mlx_base_url = (mlx_base_url or os.environ.get("FUSION_MLX_URL", "http://localhost:11432/v1")).rstrip("/")
        self.api_key = os.environ.get("FUSION_MLX_API_KEY", "local")
        self.format_checker = format_checker or DSLFormatChecker(eval_executor or DSLEvalExecutor())
        self.eval_executor = eval_executor or self.format_checker._eval_executor
        self._sxs_judge = sxs_judge

    def _get_sxs_judge(self) -> SxSJudge:
        if self._sxs_judge is None:
            self._sxs_judge = SxSJudge(SxSConfig(), base_url=self.mlx_base_url, api_key=self.api_key)
        return self._sxs_judge

    async def run(self, config: TaskConfig) -> EvalResult:
        start = time.time()
        samples = config.get("samples", [])
        if not isinstance(samples, list) or not samples:
            return EvalResult(
                task_id=config.task_id,
                executor_key=self.name,
                model=config.model,
                level="L4",
                errors=["no samples provided in config.params['samples']"],
                duration_seconds=time.time() - start,
            )
        system_prompt = config.get(
            "system_prompt", "You are a BNUP K-12 math tutor. Output <thinking> and <dsl> blocks."
        )
        cases: list[CaseResult] = []
        all_verdicts: list[SxSVerdict] = []
        dim_aggregates: dict[str, list[float]] = {
            "format": [],
            "math_accuracy": [],
            "unit_alignment": [],
            "milestone": [],
            "socratic": [],
            "ttft_ms": [],
            "tps": [],
            "kv_cache_stability": [],
        }
        errors: list[str] = []
        kv_stats = await self._collect_kv_stats()
        kv_peak_mb = kv_stats.get("peak_memory_mb", 0.0)

        for i, sample in enumerate(samples):
            try:
                output, ttft_ms, tps = await self._call_model(config.model, sample.get("prompt", ""), system_prompt)
                report = self.format_checker.run_all(output, sample.get("ground_truth"))
                math_ok, unit_ok, milestone_ok = self._eval_math(report, sample)
                verdict = await self._eval_socratic(
                    output, sample.get("reference_output", ""), sample.get("prompt", "")
                )
                all_verdicts.append(verdict)
                dim_aggregates["format"].append(float(report.pass_count) / 4.0)
                dim_aggregates["math_accuracy"].append(1.0 if math_ok else 0.0)
                dim_aggregates["unit_alignment"].append(1.0 if unit_ok else 0.0)
                dim_aggregates["milestone"].append(1.0 if milestone_ok else 0.0)
                dim_aggregates["socratic"].append(verdict.avg_a)
                dim_aggregates["ttft_ms"].append(ttft_ms)
                dim_aggregates["tps"].append(tps)
                dim_aggregates["kv_cache_stability"].append(1.0 if kv_peak_mb > 0 else 0.0)
                cases.append(
                    CaseResult(
                        input_text=sample.get("prompt", "")[:200],
                        actual=output[:200],
                        expected=str(sample.get("ground_truth", "")),
                        score=float(report.pass_count) / 4.0,
                        passed=report.all_passed and math_ok,
                        meta={
                            "format_report": report.to_dict(),
                            "math_accuracy": math_ok,
                            "unit_alignment": unit_ok,
                            "milestone": milestone_ok,
                            "socratic_scores": verdict.scores_a,
                            "ttft_ms": round(ttft_ms, 2),
                            "tps": round(tps, 2),
                            "kv_cache": kv_stats,
                        },
                    )
                )
            except Exception as e:
                errors.append(f"sample {i}: {e}")
                logger.warning("BNUP sample %d failed: %s", i, e)

        dims = {k: round(sum(v) / len(v), 4) if v else 0.0 for k, v in dim_aggregates.items()}
        sxs_agg = aggregate_verdicts(all_verdicts)
        composite = self._composite_score(dims)
        return EvalResult(
            task_id=config.task_id,
            executor_key=self.name,
            model=config.model,
            level="L4",
            metric_name="bnup_composite",
            metric_value=round(composite, 4),
            cases=cases,
            duration_seconds=time.time() - start,
            errors=errors,
            meta={"dimensions": dims, "sxs_aggregate": sxs_agg, "kv_cache": kv_stats},
        )

    def _eval_math(self, report: FormatReport, sample: dict) -> tuple[bool, bool, bool]:
        gt = sample.get("ground_truth")
        dsl_dict = report.dsl_dict
        if dsl_dict is None or report.eval_result is None:
            return False, False, False
        eval_result = report.eval_result
        math_ok = False
        if gt is not None and eval_result.final_value is not None:
            try:
                math_ok = abs(float(eval_result.final_value) - float(gt)) < _GROUND_TRUTH_TOL
            except (TypeError, ValueError):
                math_ok = False
        params = dsl_dict.get("parameters", {})
        result_units = [s.get("result_unit", "") for s in dsl_dict.get("pipeline", [])]
        unit_ok = bool(params and result_units and all(result_units))
        pipeline = dsl_dict.get("pipeline", [])
        ranges = [s.get("visual_state", {}).get("progress_range", []) for s in pipeline]
        milestone_ok = bool(
            ranges and len(ranges) >= 1 and ranges[0] and ranges[0][0] <= 0.01 and ranges[-1][-1] >= 0.99
        )
        return math_ok, unit_ok, milestone_ok

    async def _eval_socratic(self, output: str, reference: str, prompt: str) -> SxSVerdict:
        if not reference:
            return SxSVerdict(winner="a")
        judge = self._get_sxs_judge()
        return await judge.judge_pair(output, reference, prompt)

    async def _call_model(self, model: str, prompt: str, system_prompt: str) -> tuple[str, float, float]:
        if not prompt:
            raise ValueError("empty prompt")
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]
        t0 = time.time()
        ttft_ms = 0.0
        chunks: list[str] = []
        token_count = 0
        async with (
            httpx.AsyncClient(
                timeout=120.0,
                headers={"Authorization": f"Bearer {self.api_key}"},
            ) as client,
            client.stream(
                "POST",
                f"{self.mlx_base_url}/chat/completions",
                json={
                    "model": model,
                    "messages": messages,
                    "max_tokens": 2048,
                    "temperature": 0.1,
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
                    ttft_ms = (time.time() - t0) * 1000
                try:
                    chunk = json.loads(data)
                    delta = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                    if delta:
                        chunks.append(delta)
                except json.JSONDecodeError:
                    continue
                if data:
                    token_count += 1
        elapsed = time.time() - t0
        output = "".join(chunks)
        tps = token_count / max(elapsed, 0.001)
        logger.debug("BNUP model call: ttft=%.0fms tps=%.1f len=%d", ttft_ms, tps, len(output))
        return output, ttft_ms, tps

    def _composite_score(self, dims: dict[str, float]) -> float:
        # Weighted: format 0.3, math 0.2, socratic 0.2 (/5), perf 0.1 (tps/25),
        # kv_cache stability 0.1.
        socratic = dims.get("socratic", 0.0) / 5.0
        perf = min(dims.get("tps", 0.0) / 25.0, 1.0)
        return (
            0.30 * dims.get("format", 0.0)
            + 0.20 * dims.get("math_accuracy", 0.0)
            + 0.05 * dims.get("unit_alignment", 0.0)
            + 0.05 * dims.get("milestone", 0.0)
            + 0.20 * socratic
            + 0.10 * perf
            + 0.10 * dims.get("kv_cache_stability", 0.0)
        )

    async def _collect_kv_stats(self) -> dict[str, Any]:
        # Pull KV cache / memory stats from fusion-mlx /stats (Dim 4 stability).
        # Best-effort: returns zeros if server unreachable (no crash on eval).
        stats: dict[str, Any] = {"peak_memory_mb": 0.0, "memory_used": "0B", "memory_max": "unlimited", "stable": False}
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.mlx_base_url}/stats")
                if resp.status_code != 200:
                    logger.debug("KV stats: /stats returned %d", resp.status_code)
                    return stats
                data = resp.json()
            mem_used = str(data.get("model_memory_used_formatted", data.get("model_memory_used", "0B")))
            mem_max = str(data.get("model_memory_max", "unlimited"))
            peak_mb = self._parse_memory_mb(mem_used)
            stats["memory_used"] = mem_used
            stats["memory_max"] = mem_max
            stats["peak_memory_mb"] = peak_mb
            # Stable = no OOM signal + memory reported (heuristic: max not exceeded).
            stats["stable"] = peak_mb > 0 and mem_max != "0B"
            logger.debug("KV stats: peak=%.1fMB stable=%s", peak_mb, stats["stable"])
        except (httpx.HTTPError, Exception) as e:
            logger.debug("KV stats unavailable: %s", e)
        return stats

    @staticmethod
    def _parse_memory_mb(mem_str: str) -> float:
        # Parse '12.5 GB' / '800 MB' / '0B' to MB.
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

    def is_available(self) -> bool:
        return True
