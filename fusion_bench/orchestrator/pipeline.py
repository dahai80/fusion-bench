"""Pipeline — orchestrates benchmark execution across multiple tasks and executors.

Runs tasks sequentially or concurrently, collects results, applies quality gates,
and produces a unified SuiteResult.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any

from ..core.models import EvalLevel, GateResult, SuiteResult, TraceRecord, TaskStatus
from ..core.plugin_base import EvalResult, TaskConfig
from ..core.registry import executor_registry
from .gate_engine import GateEngine

logger = logging.getLogger(__name__)


class Pipeline:
    """Orchestrates a benchmark suite execution.

    1. Resolve executor plugins from registry
    2. Run tasks (sequential or concurrent)
    3. Apply quality gates
    4. Produce SuiteResult with trace records
    """

    def __init__(
        self,
        gate_engine: GateEngine | None = None,
        max_concurrent: int = 4,
        trace_callback: Any | None = None,
    ):
        self.gate_engine = gate_engine or GateEngine()
        self.max_concurrent = max_concurrent
        self.trace_callback = trace_callback
        self._trace_records: list[TraceRecord] = []

    async def run_suite(
        self,
        model: str,
        tasks: list[dict[str, Any]],
        level: str = "L1",
        suite_id: str = "",
    ) -> SuiteResult:
        """Run a full benchmark suite for a model.

        Args:
            model: Model name to benchmark.
            tasks: List of task configs, each with 'executor_key' and params.
            level: Evaluation level (L1/L2/L3/L4).
            suite_id: Optional suite identifier.
        """
        suite_id = suite_id or f"suite-{uuid.uuid4().hex[:8]}"
        eval_level = EvalLevel(level)
        start = time.time()
        results: list[dict[str, Any]] = []
        gate_results: list[GateResult] = []
        self._trace_records = []

        semaphore = asyncio.Semaphore(self.max_concurrent)

        async def _run_one(task_cfg: dict[str, Any]) -> EvalResult:
            executor_key = task_cfg.get("executor_key", "speed")
            task_id = task_cfg.get("task_id", f"{executor_key}-{uuid.uuid4().hex[:6]}")

            config = TaskConfig(
                task_id=task_id,
                model=model,
                executor_key=executor_key,
                params=task_cfg.get("params", {}),
                dataset=task_cfg.get("dataset"),
                max_samples=task_cfg.get("max_samples"),
                timeout_seconds=task_cfg.get("timeout_seconds", 600),
            )

            async with semaphore:
                try:
                    executor_cls = executor_registry.get_or_raise(executor_key)
                    executor = executor_cls()
                    result = await asyncio.wait_for(
                        executor.run(config),
                        timeout=config.timeout_seconds,
                    )
                    self._record_trace(result, TaskStatus.COMPLETED)
                    return result
                except asyncio.TimeoutError:
                    logger.error("Task %s timed out after %ds", task_id, config.timeout_seconds)
                    err_result = EvalResult(
                        task_id=task_id, executor_key=executor_key, model=model,
                        errors=[f"Timeout after {config.timeout_seconds}s"],
                    )
                    self._record_trace(err_result, TaskStatus.FAILED)
                    return err_result
                except KeyError as e:
                    logger.error("Unknown executor '%s': %s", executor_key, e)
                    err_result = EvalResult(
                        task_id=task_id, executor_key=executor_key, model=model,
                        errors=[str(e)],
                    )
                    self._record_trace(err_result, TaskStatus.FAILED)
                    return err_result
                except Exception as e:
                    logger.error("Task %s failed: %s", task_id, e)
                    err_result = EvalResult(
                        task_id=task_id, executor_key=executor_key, model=model,
                        errors=[str(e)],
                    )
                    self._record_trace(err_result, TaskStatus.FAILED)
                    return err_result

        coros = [_run_one(t) for t in tasks]
        eval_results = await asyncio.gather(*coros, return_exceptions=True)

        for er in eval_results:
            if isinstance(er, Exception):
                logger.error("Task raised: %s", er)
                results.append({"error": str(er)})
            elif isinstance(er, EvalResult):
                results.append(er.to_dict())
                gates = self.gate_engine.evaluate(
                    executor_key=er.executor_key,
                    metric_name=er.metric_name,
                    metric_value=er.metric_value,
                    level=eval_level,
                )
                gate_results.extend(gates)

        overall_passed = all(g.passed for g in gate_results) if gate_results else True

        suite = SuiteResult(
            suite_id=suite_id,
            model=model,
            level=eval_level,
            results=results,
            gate_results=gate_results,
            overall_passed=overall_passed,
            duration_seconds=time.time() - start,
        )

        logger.info("Suite %s completed: %d tasks, %d gates, passed=%s, %.1fs",
                     suite_id, len(results), len(gate_results), overall_passed, suite.duration_seconds)

        return suite

    def _record_trace(self, result: EvalResult, status: TaskStatus) -> None:
        record = TraceRecord(
            trace_id=f"trace-{uuid.uuid4().hex[:8]}",
            model=result.model,
            level=EvalLevel(result.level),
            executor_key=result.executor_key,
            task_id=result.task_id,
            status=status,
            eval_result=result.to_dict(),
            duration_seconds=result.duration_seconds,
        )
        self._trace_records.append(record)
        if self.trace_callback:
            try:
                self.trace_callback(record)
            except Exception as e:
                logger.warning("Trace callback failed: %s", e)

    @property
    def trace_records(self) -> list[TraceRecord]:
        return list(self._trace_records)
