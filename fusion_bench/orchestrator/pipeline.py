"""Pipeline — orchestrates benchmark execution across multiple tasks and executors.

Runs tasks sequentially or concurrently, collects results, applies quality gates,
and produces a unified SuiteResult. Supports retry, checkpoint, and cancellation.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any

from ..api.gpu_monitor import GPUStats, get_gpu_stats
from ..api.sse import get_progress_stream
from ..cache import BenchmarkCache
from ..core.models import EvalLevel, GateResult, SuiteResult, TaskStatus, TraceRecord
from ..core.plugin_base import EvalResult, TaskConfig
from ..core.registry import executor_registry
from .circuit_breaker import CircuitBreaker
from .gate_engine import GateEngine
from .root_cause import analyze as root_cause_analyze

logger = logging.getLogger(__name__)

_DEFAULT_CHECKPOINT_DIR = Path.home() / ".fusion-bench" / "checkpoints"

_EVAL_RESULT_FIELDS = {
    "task_id",
    "executor_key",
    "model",
    "level",
    "metric_name",
    "metric_value",
    "cases",
    "duration_seconds",
    "errors",
    "meta",
    "failure_category",
    "failure_detail",
    "optimization_hints",
}


def _is_deterministic(config: TaskConfig) -> bool:
    # Cache only safe when temperature=0, fixed seed, bounded samples.
    params = config.params or {}
    temp = params.get("temperature", params.get("temp", 0))
    if temp not in (0, 0.0):
        return False
    return config.max_samples is not None


class Pipeline:
    """Orchestrates a benchmark suite execution.

    Supports:
    - max_retries: auto-retry failed tasks
    - checkpoint_dir: persist progress for resume
    - cancel(): cancel a running suite
    - pause()/resume(): pause and resume task execution
    - event triggers: run on model registration/update events
    """

    def __init__(
        self,
        gate_engine: GateEngine | None = None,
        max_concurrent: int = 4,
        trace_callback: Any | None = None,
        max_retries: int = 2,
        checkpoint_dir: str | Path | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        cache: BenchmarkCache | None = None,
        use_cache: bool = True,
    ):
        self.gate_engine = gate_engine or GateEngine()
        self.max_concurrent = max_concurrent
        self.trace_callback = trace_callback
        self.max_retries = max_retries
        self.checkpoint_dir = Path(checkpoint_dir) if checkpoint_dir else _DEFAULT_CHECKPOINT_DIR
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self.circuit_breaker = circuit_breaker or CircuitBreaker()
        self.cache = cache
        self.use_cache = use_cache
        self._trace_records: list[TraceRecord] = []
        self._cancelled = False
        self._paused = False
        self._pause_event: asyncio.Event | None = None
        self._suite_id = ""
        self._event_handlers: dict[str, list[Any]] = {}
        self._pipeline_triggers: list[dict[str, Any]] = []
        self._gpu_overload_threshold: float = 95.0
        self._gpu_memory_threshold: float = 95.0
        self._last_gpu_stats: GPUStats | None = None

    def cancel(self) -> None:
        logger.info("Pipeline cancellation requested for suite %s", self._suite_id)
        self._cancelled = True

    def pause(self) -> None:
        logger.info("Pipeline pause requested for suite %s", self._suite_id)
        self._paused = True
        if self._pause_event:
            self._pause_event.clear()

    def resume(self) -> None:
        logger.info("Pipeline resume requested for suite %s", self._suite_id)
        self._paused = False
        if self._pause_event:
            self._pause_event.set()

    @property
    def is_paused(self) -> bool:
        return self._paused

    def on_event(self, event_type: str, handler: Any) -> None:
        self._event_handlers.setdefault(event_type, []).append(handler)

    async def trigger_event(self, event_type: str, payload: dict[str, Any] | None = None) -> list[Any]:
        handlers = self._event_handlers.get(event_type, [])
        results = []
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    result = await handler(payload or {})
                else:
                    result = handler(payload or {})
                results.append(result)
            except Exception as e:
                logger.warning("Event handler %s failed: %s", handler, e)
        return results

    def add_trigger(self, condition: str, action: str, params: dict[str, Any] | None = None) -> None:
        self._pipeline_triggers.append(
            {
                "condition": condition,
                "action": action,
                "params": params or {},
            }
        )
        logger.info("Added pipeline trigger: %s -> %s", condition, action)

    async def _check_triggers(self, result: EvalResult) -> list[Any]:
        triggered = []
        for trigger in self._pipeline_triggers:
            if self._evaluate_trigger_condition(trigger["condition"], result):
                logger.info(
                    "Pipeline trigger fired: %s -> %s",
                    trigger["condition"],
                    trigger["action"],
                )
                trigger_results = await self.trigger_event(
                    trigger["action"],
                    {
                        "source_result": result.to_dict(),
                        "trigger_condition": trigger["condition"],
                        **trigger["params"],
                    },
                )
                triggered.extend(trigger_results)
        return triggered

    @staticmethod
    def _evaluate_trigger_condition(condition: str, result: EvalResult) -> bool:
        try:
            parts = condition.split(":", 1)
            field = parts[0]
            op_and_val = parts[1] if len(parts) > 1 else ""

            value = None
            if field == "metric_value":
                value = result.metric_value
            elif field == "metric_name":
                value = result.metric_name
            elif field == "executor_key":
                value = result.executor_key
            elif field == "has_errors":
                value = bool(result.errors)
            elif field == "model":
                value = result.model

            if value is None:
                return False

            if not op_and_val:
                return bool(value)

            if op_and_val.startswith(">="):
                return float(value) >= float(op_and_val[2:])
            elif op_and_val.startswith("<="):
                return float(value) <= float(op_and_val[2:])
            elif op_and_val.startswith(">"):
                return float(value) > float(op_and_val[1:])
            elif op_and_val.startswith("<"):
                return float(value) < float(op_and_val[1:])
            elif op_and_val.startswith("=="):
                return str(value) == op_and_val[2:]
            elif op_and_val.startswith("!="):
                return str(value) != op_and_val[2:]
            return str(value) == op_and_val
        except Exception as e:
            logger.warning("Trigger condition eval failed '%s': %s", condition, e)
            return False

    async def check_gpu_overload(self, mlx_base_url: str = "http://localhost:11432/v1") -> bool:
        try:
            stats = await get_gpu_stats(mlx_base_url)
            self._last_gpu_stats = stats
            if stats.utilization_pct >= self._gpu_overload_threshold:
                logger.warning(
                    "GPU overload detected: utilization=%.1f%% >= %.1f%%",
                    stats.utilization_pct,
                    self._gpu_overload_threshold,
                )
                return True
            if stats.memory_total_gb > 0:
                mem_pct = (stats.memory_used_gb / stats.memory_total_gb) * 100
                if mem_pct >= self._gpu_memory_threshold:
                    logger.warning(
                        "GPU memory overload: %.1f%% used >= %.1f%% threshold",
                        mem_pct,
                        self._gpu_memory_threshold,
                    )
                    return True
            return False
        except Exception as e:
            logger.debug("GPU overload check failed: %s", e)
            return False

    @property
    def last_gpu_stats(self) -> GPUStats | None:
        return self._last_gpu_stats

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled

    def _checkpoint_path(self, suite_id: str) -> Path:
        return self.checkpoint_dir / f"{suite_id}.json"

    def _save_checkpoint(
        self,
        suite_id: str,
        completed: dict[str, EvalResult],
        remaining: list[dict[str, Any]],
    ) -> None:
        gpu_snapshot = None
        if self._last_gpu_stats:
            gpu_snapshot = self._last_gpu_stats.to_dict()

        error_contexts = {}
        for tid, r in completed.items():
            if r.errors:
                error_contexts[tid] = {
                    "errors": r.errors,
                    "metric_name": r.metric_name,
                    "metric_value": r.metric_value,
                    "executor_key": r.executor_key,
                    "failure_analysis": r.to_dict().get("failure_analysis", {}),
                }

        data = {
            "suite_id": suite_id,
            "completed": {tid: r.to_dict() for tid, r in completed.items()},
            "remaining": remaining,
            "error_contexts": error_contexts,
            "gpu_snapshot": gpu_snapshot,
            "circuit_breaker_states": self.circuit_breaker.list_circuits(),
            "pipeline_state": {
                "paused": self._paused,
                "cancelled": self._cancelled,
            },
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "version": 2,
        }
        path = self._checkpoint_path(suite_id)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        logger.debug(
            "Checkpoint saved: %s (%d done, %d remaining, gpu=%s, errors=%d)",
            suite_id,
            len(completed),
            len(remaining),
            "yes" if gpu_snapshot else "no",
            len(error_contexts),
        )

    def load_checkpoint(self, suite_id: str) -> dict[str, Any] | None:
        path = self._checkpoint_path(suite_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            logger.info(
                "Loaded checkpoint: %s (%d done, %d remaining, v%d)",
                suite_id,
                len(data.get("completed", {})),
                len(data.get("remaining", [])),
                data.get("version", 1),
            )

            if data.get("version", 1) >= 2:
                for cb_state in data.get("circuit_breaker_states", []):
                    ek = cb_state.get("executor_key", "")
                    if cb_state.get("state") == "open":
                        self.circuit_breaker.record_failure(
                            ek,
                            cb_state.get("last_failure_msg", "restored from checkpoint"),
                        )
                    elif ek:
                        self.circuit_breaker.reset(ek)

                pipeline_state = data.get("pipeline_state", {})
                self._cancelled = pipeline_state.get("cancelled", False)

                if data.get("gpu_snapshot"):
                    with contextlib.suppress(Exception):
                        self._last_gpu_stats = GPUStats(**data["gpu_snapshot"])

            return data
        except (json.JSONDecodeError, OSError) as e:
            logger.error("Failed to load checkpoint %s: %s", suite_id, e)
            return None

    def _remove_checkpoint(self, suite_id: str) -> None:
        path = self._checkpoint_path(suite_id)
        if path.exists():
            path.unlink()
            logger.debug("Checkpoint removed: %s", suite_id)

    async def run_suite(
        self,
        model: str,
        tasks: list[dict[str, Any]],
        level: str = "L1",
        suite_id: str = "",
        resume: bool = False,
    ) -> SuiteResult:
        suite_id = suite_id or f"suite-{uuid.uuid4().hex[:8]}"
        self._suite_id = suite_id
        self._pause_event = asyncio.Event()
        self._pause_event.set()
        self._cancelled = False
        eval_level = EvalLevel(level)
        start = time.time()
        results: list[dict[str, Any]] = []
        gate_results: list[GateResult] = []
        self._trace_records = []
        stream = get_progress_stream()
        stream.emit(
            suite_id,
            "suite_started",
            {
                "suite_id": suite_id,
                "model": model,
                "level": level,
                "task_count": len(tasks),
                "ts": time.strftime("%H:%M:%S"),
            },
        )

        completed: dict[str, EvalResult] = {}
        remaining = sorted(tasks, key=lambda t: t.get("priority", 0), reverse=True)

        if resume:
            ckpt = self.load_checkpoint(suite_id)
            if ckpt:
                for tid, rdict in ckpt.get("completed", {}).items():
                    completed[tid] = EvalResult(
                        task_id=rdict.get("task_id", tid),
                        executor_key=rdict.get("executor_key", ""),
                        model=rdict.get("model", model),
                        level=rdict.get("level", level),
                        metric_name=rdict.get("metric_name", ""),
                        metric_value=rdict.get("metric_value", 0.0),
                        errors=rdict.get("errors", []),
                    )
                remaining = ckpt.get("remaining", remaining)
                logger.info(
                    "Resuming suite %s: %d completed, %d remaining",
                    suite_id,
                    len(completed),
                    len(remaining),
                )

        semaphore = asyncio.Semaphore(self.max_concurrent)

        async def _run_one_with_retry(task_cfg: dict[str, Any]) -> EvalResult:
            executor_key = task_cfg.get("executor_key", "speed")
            task_id = task_cfg.get("task_id", f"{executor_key}-{uuid.uuid4().hex[:6]}")

            if task_id in completed:
                logger.info("Skipping completed task: %s", task_id)
                return completed[task_id]

            config = TaskConfig(
                task_id=task_id,
                model=model,
                executor_key=executor_key,
                params=task_cfg.get("params", {}),
                dataset=task_cfg.get("dataset"),
                max_samples=task_cfg.get("max_samples"),
                timeout_seconds=task_cfg.get("timeout_seconds", 600),
                priority=task_cfg.get("priority", 0),
            )

            if self.use_cache and self.cache and _is_deterministic(config):
                cached = self.cache.get(model, config.params, task_id, executor_key)
                if cached:
                    logger.info("Cache hit for task %s executor %s", task_id, executor_key)
                    stream.emit(suite_id, "cache_hit", {"task_id": task_id, "executor_key": executor_key})
                    cached_result = EvalResult(**{k: v for k, v in cached.items() if k in _EVAL_RESULT_FIELDS})
                    completed[task_id] = cached_result
                    return cached_result
                logger.debug("Cache miss for task %s", task_id)

            if not self.circuit_breaker.can_execute(executor_key):
                cb_state = self.circuit_breaker.get_state(executor_key)
                logger.warning("Circuit OPEN for %s, skipping task %s", executor_key, task_id)
                cb_result = EvalResult(
                    task_id=task_id,
                    executor_key=executor_key,
                    model=model,
                    errors=[f"Circuit breaker OPEN for {executor_key}: state={cb_state}"],
                )
                cb_result.analyze_failure()
                self._record_trace(cb_result, TaskStatus.FAILED)
                return cb_result

            last_result = None
            for attempt in range(1, self.max_retries + 2):
                if self._cancelled:
                    err_result = EvalResult(
                        task_id=task_id,
                        executor_key=executor_key,
                        model=model,
                        errors=["Cancelled by user"],
                    )
                    err_result.analyze_failure()
                    self._record_trace(err_result, TaskStatus.FAILED)
                    return err_result

                if self._paused and self._pause_event:
                    await self._pause_event.wait()

                if await self.check_gpu_overload():
                    logger.info("GPU overloaded, waiting 10s before task %s", task_id)
                    await asyncio.sleep(10)
                    if await self.check_gpu_overload():
                        logger.warning("GPU still overloaded, skipping task %s", task_id)
                        gpu_result = EvalResult(
                            task_id=task_id,
                            executor_key=executor_key,
                            model=model,
                            errors=["GPU overload detected, task deferred"],
                        )
                        gpu_result.analyze_failure()
                        self._record_trace(gpu_result, TaskStatus.FAILED)
                        return gpu_result

                async with semaphore:
                    try:
                        executor_cls = executor_registry.get_or_raise(executor_key)
                        executor = executor_cls()
                        result = await asyncio.wait_for(
                            executor.run(config),
                            timeout=config.timeout_seconds,
                        )
                        self.circuit_breaker.record_success(executor_key)
                        self._record_trace(result, TaskStatus.COMPLETED)
                        if self.use_cache and self.cache and _is_deterministic(config):
                            with contextlib.suppress(Exception):
                                self.cache.set(model, config.params, task_id, executor_key, result.to_dict())
                        completed[task_id] = result
                        self._save_checkpoint(suite_id, completed, remaining)
                        if self._pipeline_triggers:
                            await self._check_triggers(result)
                        stream.emit(
                            suite_id,
                            "task_completed",
                            {
                                "task_id": task_id,
                                "executor_key": executor_key,
                                "metric_name": result.metric_name,
                                "metric_value": result.metric_value,
                                "progress": f"{len(completed)}/{len(remaining)}",
                                "ts": time.strftime("%H:%M:%S"),
                            },
                        )
                        return result
                    except TimeoutError:
                        logger.error(
                            "Task %s timed out (attempt %d/%d)",
                            task_id,
                            attempt,
                            self.max_retries + 1,
                        )
                        self.circuit_breaker.record_failure(executor_key, "timeout")
                        last_result = EvalResult(
                            task_id=task_id,
                            executor_key=executor_key,
                            model=model,
                            errors=[f"Timeout after {config.timeout_seconds}s (attempt {attempt})"],
                        )
                    except KeyError as e:
                        logger.error("Unknown executor '%s': %s", executor_key, e)
                        self.circuit_breaker.record_failure(executor_key, str(e))
                        last_result = EvalResult(
                            task_id=task_id,
                            executor_key=executor_key,
                            model=model,
                            errors=[str(e)],
                        )
                        last_result.analyze_failure()
                        self._record_trace(last_result, TaskStatus.FAILED)
                        return last_result
                    except Exception as e:
                        logger.error(
                            "Task %s failed (attempt %d/%d): %s",
                            task_id,
                            attempt,
                            self.max_retries + 1,
                            e,
                        )
                        self.circuit_breaker.record_failure(executor_key, str(e))
                        last_result = EvalResult(
                            task_id=task_id,
                            executor_key=executor_key,
                            model=model,
                            errors=[f"{e} (attempt {attempt})"],
                        )

                if attempt <= self.max_retries:
                    logger.info("Retrying task %s in 2s...", task_id)
                    await asyncio.sleep(2)

            last_result.analyze_failure()
            self._record_trace(last_result, TaskStatus.FAILED)
            completed[task_id] = last_result
            self._save_checkpoint(suite_id, completed, remaining)
            stream.emit(
                suite_id,
                "task_failed",
                {
                    "task_id": task_id,
                    "executor_key": executor_key,
                    "errors": last_result.errors,
                    "progress": f"{len(completed)}/{len(remaining)}",
                    "ts": time.strftime("%H:%M:%S"),
                },
            )
            return last_result

        coros = [_run_one_with_retry(t) for t in remaining]
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
                for g in gates:
                    stream.emit(
                        suite_id,
                        "gate_result",
                        {
                            "gate_id": g.gate_id,
                            "gate_name": g.gate_name,
                            "passed": g.passed,
                            "action": g.action,
                            "metric_value": g.metric_value,
                            "threshold": g.threshold,
                            "ts": time.strftime("%H:%M:%S"),
                        },
                    )

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

        if not self._cancelled:
            self._remove_checkpoint(suite_id)

        logger.info(
            "Suite %s completed: %d tasks, %d gates, passed=%s, %.1fs",
            suite_id,
            len(results),
            len(gate_results),
            overall_passed,
            suite.duration_seconds,
        )
        stream.emit(
            suite_id,
            "suite_completed",
            {
                "suite_id": suite_id,
                "overall_passed": overall_passed,
                "task_count": len(results),
                "gate_count": len(gate_results),
                "duration_seconds": round(suite.duration_seconds, 2),
                "ts": time.strftime("%H:%M:%S"),
            },
        )

        return suite

    def _record_trace(self, result: EvalResult, status: TaskStatus) -> None:
        eval_dict = result.to_dict()
        if status == TaskStatus.FAILED and result.errors:
            rca = root_cause_analyze(
                errors=result.errors,
                executor_key=result.executor_key,
                metric_value=result.metric_value,
                metric_name=result.metric_name,
            )
            eval_dict["root_cause"] = rca.to_dict()
            logger.info(
                "Root cause for %s: category=%s confidence=%.2f",
                result.task_id,
                rca.failure_category,
                rca.confidence,
            )
        record = TraceRecord(
            trace_id=f"trace-{uuid.uuid4().hex[:8]}",
            model=result.model,
            level=EvalLevel(result.level),
            executor_key=result.executor_key,
            task_id=result.task_id,
            status=status,
            eval_result=eval_dict,
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
