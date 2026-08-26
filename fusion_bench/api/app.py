"""FastAPI application for Fusion-Bench REST API.

Implements PRD Section 8: task management, suite management,
results/analysis, quality gates, and system management.
"""

from __future__ import annotations

import asyncio
import logging
import os as _os
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, Field, model_validator

from ..auth.identity import IdentityMiddleware
from ..auth.rbac import Permission, require_permission
from ..core.models import EvalLevel, GateTier, TaskStatus
from ..storage.trace_store import TraceStore

if _os.environ.get("FUSION_BENCH_TLS_ENFORCE") == "1":
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request
    from starlette.responses import JSONResponse

    class _TLSRedirectMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            scheme = request.url.scheme
            if scheme == "http":
                return JSONResponse(
                    status_code=426,
                    content={"detail": "TLS required. Use HTTPS."},
                    headers={"Upgrade": "TLS"},
                )
            return await call_next(request)


logger = logging.getLogger(__name__)

_store: TraceStore | None = None
_background_tasks: dict[str, dict[str, Any]] = {}


def _get_store() -> TraceStore:
    global _store
    if _store is None:
        _store = TraceStore()
    return _store


@asynccontextmanager
async def lifespan(app: FastAPI):
    _get_store()
    yield
    if _store:
        _store.close()


app = FastAPI(
    title="Fusion-Bench API",
    version="0.4.0rc1",
    description="Fusion-Bench — MLX model benchmarking REST API",
    lifespan=lifespan,
)

if _os.environ.get("FUSION_BENCH_TLS_ENFORCE") == "1":
    app.add_middleware(_TLSRedirectMiddleware)
    logger.info("TLS enforcement middleware enabled — HTTP requests will be rejected")

app.add_middleware(IdentityMiddleware)
logger.info("Identity middleware registered")


# ── Request/Response schemas ────────────────────────────────────────


class TaskCreateRequest(BaseModel):
    task_type: str = Field(default="model", description="Task type: model/agent/code/security/artifact")
    model: str = Field(default="qwen3.5-9b")
    model_id: str | None = Field(default=None, description="External model UUID (e.g. from fusion-model-hub)")
    suite_id: str | None = None
    suite: str | None = Field(default=None, description="Suite alias: standard/full/quick — maps to executor_key")
    executor_key: str = Field(default="speed")
    callback_url: str | None = Field(default=None, description="POST result to this URL on completion")
    params: dict[str, Any] = Field(default_factory=dict)
    dataset: str | None = None
    max_samples: int | None = None
    timeout_seconds: int = 600
    level: str = Field(default="L1")

    _SUITE_MAP: dict[str, str] = {
        "quick": "speed",
        "standard": "speed",
        "full": "speed",
    }

    @model_validator(mode="after")
    def _resolve_suite(self) -> TaskCreateRequest:
        if self.suite and self.executor_key == "speed":
            mapped = self._SUITE_MAP.get(self.suite)
            if mapped:
                self.executor_key = mapped
        return self


class TaskResponse(BaseModel):
    task_id: str
    status: str
    model: str
    model_id: str | None = None
    executor_key: str
    level: str
    created_at: str


class TaskDetailResponse(TaskResponse):
    progress: float = 0.0
    result: dict[str, Any] | None = None
    error: str | None = None
    duration_seconds: float = 0.0


class SuiteInfoResponse(BaseModel):
    suite_id: str
    name: str
    task_count: int
    level: str


class SuiteCreateRequest(BaseModel):
    name: str = Field(description="Suite display name")
    tasks: list[dict[str, Any]] = Field(default_factory=list, description="List of task definitions")
    level: str = Field(default="L1", description="Evaluation level (L1–L4)")


class CaseUploadRequest(BaseModel):
    cases: list[dict[str, Any]] = Field(description="List of test cases to upload")


class CaseResponse(BaseModel):
    input_text: str = ""
    expected: str = ""
    actual: str = ""
    score: float = 0.0
    passed: bool = False
    latency_ms: float = 0.0
    meta: dict[str, Any] = Field(default_factory=dict)


class ResultResponse(BaseModel):
    task_id: str
    model: str
    executor_key: str
    level: str
    metric_name: str
    metric_value: float
    pass_rate: float
    num_cases: int
    duration_seconds: float
    errors: list[str]
    meta: dict[str, Any]


class GateCheckRequest(BaseModel):
    task_id: str
    gate_id: str | None = None
    tier: str | None = None


class GateCheckResponse(BaseModel):
    passed: bool
    gates: list[dict[str, Any]]


class GateRuleCreate(BaseModel):
    name: str
    tier: str = "experimental"
    metric_name: str
    operator: str = ">="
    threshold: float = 0.0
    executor_key: str | None = None
    level: str | None = None


class GateApproveRequest(BaseModel):
    approver: str
    remark: str = ""


class CompareRequest(BaseModel):
    task_ids: list[str]


class TrendPoint(BaseModel):
    timestamp: str
    metric_value: float
    model: str
    executor_key: str


class HealthResponse(BaseModel):
    status: str
    uptime_seconds: float
    active_tasks: int
    store_total: int


_start_time = time.time()


# ── Task Management ─────────────────────────────────────────────────


@app.post("/api/v1/tasks", response_model=TaskResponse, status_code=201)
async def create_task(
    req: TaskCreateRequest,
    _user: str = Depends(require_permission(Permission.TASK_CREATE)),
):
    task_id = f"task-{uuid.uuid4().hex[:8]}"
    record = {
        "task_id": task_id,
        "status": "pending",
        "model": req.model,
        "executor_key": req.executor_key,
        "level": req.level,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "request": req.model_dump(),
    }
    _background_tasks[task_id] = record
    asyncio.create_task(_run_task(task_id, req))
    logger.info("Created task %s for model=%s executor=%s", task_id, req.model, req.executor_key)
    return TaskResponse(
        task_id=task_id,
        status="pending",
        model=req.model,
        model_id=req.model_id,
        executor_key=req.executor_key,
        level=req.level,
        created_at=record["created_at"],
    )


async def _run_task(task_id: str, req: TaskCreateRequest):
    info = _background_tasks.get(task_id)
    if not info:
        return
    info["status"] = "running"
    try:
        from ..core.plugin_base import TaskConfig
        from ..core.registry import executor_registry
        from ..executors import register_all

        register_all()

        config = TaskConfig(
            task_id=task_id,
            model=req.model,
            executor_key=req.executor_key,
            params=req.params,
            dataset=req.dataset,
            max_samples=req.max_samples,
            timeout_seconds=req.timeout_seconds,
        )
        executor_cls = executor_registry.get_or_raise(req.executor_key)
        executor = executor_cls()
        result = await asyncio.wait_for(executor.run(config), timeout=req.timeout_seconds)
        info["status"] = "completed"
        info["result"] = result.to_dict()
        info["duration_seconds"] = result.duration_seconds
        info["progress"] = 1.0

        from ..core.models import TraceRecord

        trace = TraceRecord(
            trace_id=f"trace-{uuid.uuid4().hex[:8]}",
            model=req.model,
            level=EvalLevel(req.level),
            executor_key=req.executor_key,
            task_id=task_id,
            status=TaskStatus.COMPLETED,
            eval_result=result.to_dict(),
            duration_seconds=result.duration_seconds,
        )
        _get_store().insert(trace)
    except TimeoutError:
        info["status"] = "failed"
        info["error"] = f"Timeout after {req.timeout_seconds}s"
        logger.error("Task %s timed out", task_id)
    except Exception as e:
        info["status"] = "failed"
        info["error"] = str(e)
        logger.error("Task %s failed: %s", task_id, e)
    finally:
        cb_url = req.callback_url
        if cb_url:
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    await client.post(
                        cb_url,
                        json={
                            "task_id": task_id,
                            "status": info.get("status", "unknown"),
                            "model": req.model,
                            "model_id": req.model_id,
                            "executor_key": req.executor_key,
                            "result": info.get("result"),
                            "error": info.get("error"),
                            "duration_seconds": info.get("duration_seconds", 0),
                        },
                    )
                logger.info("Callback POST to %s for task %s", cb_url, task_id)
            except Exception as cb_err:
                logger.warning("Callback POST failed for task %s: %s", task_id, cb_err)


@app.get("/api/v1/tasks", response_model=list[TaskResponse])
async def list_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = None,
    model: str | None = None,
):
    store = _get_store()
    records = store.query(model=model, status=status, limit=page_size * page)
    items = []
    for r in records:
        items.append(
            TaskResponse(
                task_id=r.trace_id,
                status=r.status.value,
                model=r.model,
                executor_key=r.executor_key,
                level=r.level.value,
                created_at=r.timestamp[:19],
            )
        )
    for tid, info in _background_tasks.items():
        if model and info.get("model") != model:
            continue
        if status and info.get("status") != status:
            continue
        items.append(
            TaskResponse(
                task_id=tid,
                status=info.get("status", "unknown"),
                model=info.get("model", ""),
                executor_key=info.get("executor_key", ""),
                level=info.get("level", "L1"),
                created_at=info.get("created_at", ""),
            )
        )
    start = (page - 1) * page_size
    return items[start : start + page_size]


@app.get("/api/v1/tasks/{task_id}", response_model=TaskDetailResponse)
async def get_task(task_id: str):
    info = _background_tasks.get(task_id)
    if info:
        return TaskDetailResponse(
            task_id=task_id,
            status=info.get("status", "unknown"),
            model=info.get("model", ""),
            executor_key=info.get("executor_key", ""),
            level=info.get("level", "L1"),
            created_at=info.get("created_at", ""),
            progress=info.get("progress", 0.0),
            result=info.get("result"),
            error=info.get("error"),
            duration_seconds=info.get("duration_seconds", 0.0),
        )
    store = _get_store()
    records = store.query(limit=1000)
    for r in records:
        if r.trace_id == task_id or r.task_id == task_id:
            return TaskDetailResponse(
                task_id=r.task_id,
                status=r.status.value,
                model=r.model,
                executor_key=r.executor_key,
                level=r.level.value,
                created_at=r.timestamp[:19],
                progress=1.0 if r.status == TaskStatus.COMPLETED else 0.0,
                result=r.eval_result,
                error=r.error_message,
                duration_seconds=r.duration_seconds,
            )
    raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")


@app.post("/api/v1/tasks/{task_id}/cancel")
async def cancel_task(task_id: str, _user: str = Depends(require_permission(Permission.TASK_CANCEL))):
    info = _background_tasks.get(task_id)
    if not info:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
    if info.get("status") not in ("pending", "running"):
        raise HTTPException(status_code=400, detail=f"Task is {info['status']}, cannot cancel")
    info["status"] = "cancelled"
    info["error"] = "Cancelled by user"
    return {"task_id": task_id, "status": "cancelled"}


@app.post("/api/v1/tasks/{task_id}/retry", response_model=TaskResponse)
async def retry_task(task_id: str):
    info = _background_tasks.get(task_id)
    if not info:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
    if info.get("status") not in ("failed", "cancelled"):
        raise HTTPException(status_code=400, detail="Only failed/cancelled tasks can be retried")
    req_data = info.get("request", {})
    req = TaskCreateRequest(**req_data)
    new_id = f"task-{uuid.uuid4().hex[:8]}"
    new_info = {
        "task_id": new_id,
        "status": "pending",
        "model": req.model,
        "executor_key": req.executor_key,
        "level": req.level,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "request": req.model_dump(),
    }
    _background_tasks[new_id] = new_info
    asyncio.create_task(_run_task(new_id, req))
    return TaskResponse(
        task_id=new_id,
        status="pending",
        model=req.model,
        executor_key=req.executor_key,
        level=req.level,
        created_at=new_info["created_at"],
    )


@app.get("/api/v1/tasks/{task_id}/logs")
async def get_task_logs(task_id: str, line_count: int = Query(50, ge=1, le=500)):
    info = _background_tasks.get(task_id)
    if not info:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
    lines = [f"[{info.get('created_at', '')}] Task {task_id} created"]
    if info.get("error"):
        lines.append(f"[ERROR] {info['error']}")
    if info.get("result"):
        lines.append(f"[RESULT] metric={info['result'].get('metric_name')} value={info['result'].get('metric_value')}")
    return {"task_id": task_id, "lines": lines[-line_count:]}


# ── Suite Management ────────────────────────────────────────────────


@app.get("/api/v1/suites", response_model=list[SuiteInfoResponse])
async def list_suites():
    from ..executors import register_all
    from ..orchestrator.scheduler import Scheduler

    register_all()
    scheduler = Scheduler()
    scheduler.load_default_suites()
    items = []
    for name in scheduler.list_suites():
        tasks = scheduler.get_suite(name)
        level = tasks[0].level.value if tasks else "L1"
        items.append(
            SuiteInfoResponse(
                suite_id=name,
                name=name,
                task_count=len(tasks),
                level=level,
            )
        )
    return items


@app.get("/api/v1/suites/{suite_id}")
async def get_suite(suite_id: str):
    from ..executors import register_all
    from ..orchestrator.scheduler import Scheduler

    register_all()
    scheduler = Scheduler()
    scheduler.load_default_suites()
    try:
        tasks = scheduler.get_suite(suite_id)
    except KeyError as err:
        raise HTTPException(status_code=404, detail=f"Suite '{suite_id}' not found") from err
    return {
        "suite_id": suite_id,
        "name": suite_id,
        "tasks": [t.to_dict() for t in tasks],
        "task_count": len(tasks),
    }


@app.post("/api/v1/suites", status_code=201)
async def create_suite(
    req: SuiteCreateRequest,
    _user: str = Depends(require_permission(Permission.BASELINE_MANAGE)),
):
    from ..core.models import BenchmarkTask, EvalLevel
    from ..orchestrator.scheduler import Scheduler

    scheduler = Scheduler()
    scheduler.load_default_suites()
    level = EvalLevel(req.level)
    tasks = []
    for i, t in enumerate(req.tasks):
        bt = BenchmarkTask(
            task_id=t.get("task_id", f"custom-{uuid.uuid4().hex[:6]}"),
            name=t.get("name", f"Task {i + 1}"),
            level=level,
            executor_key=t.get("executor_key", "speed"),
            dataset=t.get("dataset"),
            max_samples=t.get("max_samples"),
            params=t.get("params", {}),
            timeout_seconds=t.get("timeout_seconds", 600),
        )
        tasks.append(bt)
    scheduler.register_suite(req.name, tasks)
    logger.info("Created custom suite '%s' with %d tasks", req.name, len(tasks))
    return {
        "suite_id": req.name,
        "name": req.name,
        "task_count": len(tasks),
        "created": True,
    }


@app.post("/api/v1/suites/{suite_id}/cases", status_code=201)
async def upload_suite_cases(
    suite_id: str,
    req: CaseUploadRequest,
    _user: str = Depends(require_permission(Permission.DATASET_MANAGE)),
):
    from ..storage.dataset_store import DatasetStore

    store = DatasetStore()
    ds_id = store.create(
        name=f"suite-{suite_id}-cases",
        items=req.cases,
        description=f"Cases for suite {suite_id}",
        format="qa",
    )
    logger.info(
        "Uploaded %d cases for suite %s (dataset_id=%s)",
        len(req.cases),
        suite_id,
        ds_id,
    )
    return {"dataset_id": ds_id, "suite_id": suite_id, "uploaded": len(req.cases)}


@app.get("/api/v1/suites/{suite_id}/cases")
async def list_suite_cases(suite_id: str, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
    from ..storage.dataset_store import DatasetStore

    store = DatasetStore()
    datasets = store.list_datasets(limit=100)
    matched = [d for d in datasets if d.get("name") == f"suite-{suite_id}-cases"]
    if not matched:
        return {"suite_id": suite_id, "cases": [], "total": 0, "page": page}
    ds = store.get(matched[0]["dataset_id"])
    items = ds.get("items", []) if ds else []
    start = (page - 1) * page_size
    return {
        "suite_id": suite_id,
        "cases": items[start : start + page_size],
        "total": len(items),
        "page": page,
    }


# ── Results & Analysis ──────────────────────────────────────────────


@app.get("/api/v1/results/{task_id}", response_model=ResultResponse)
async def get_result(task_id: str):
    store = _get_store()
    records = store.query(limit=1000)
    for r in records:
        if r.trace_id == task_id or r.task_id == task_id:
            er = r.eval_result or {}
            return ResultResponse(
                task_id=r.task_id,
                model=r.model,
                executor_key=r.executor_key,
                level=r.level.value,
                metric_name=er.get("metric_name", ""),
                metric_value=er.get("metric_value", 0.0),
                pass_rate=er.get("pass_rate", 0.0),
                num_cases=er.get("num_cases", 0),
                duration_seconds=r.duration_seconds,
                errors=er.get("errors", []),
                meta=er.get("meta", {}),
            )
    raise HTTPException(status_code=404, detail=f"Result for '{task_id}' not found")


@app.post("/api/v1/results/compare")
async def compare_results(req: CompareRequest):
    store = _get_store()
    results = []
    for tid in req.task_ids:
        records = store.query(limit=1000)
        for r in records:
            if r.trace_id == tid or r.task_id == tid:
                results.append({"task_id": tid, "result": r.eval_result})
                break
    if len(results) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 results to compare")
    return {"compared": results}


@app.post("/api/v1/results/{task_id}/export")
async def export_result(task_id: str, format: str = Query("json", pattern="^(json|markdown|html)$")):
    store = _get_store()
    records = store.query(limit=1000)
    for r in records:
        if r.trace_id == task_id or r.task_id == task_id:
            if format == "markdown":
                er = r.eval_result or {}
                md = f"# Benchmark Result: {task_id}\n\n"
                md += f"- **Model**: {r.model}\n- **Executor**: {r.executor_key}\n"
                md += f"- **Metric**: {er.get('metric_name', 'N/A')} = {er.get('metric_value', 0):.4f}\n"
                md += f"- **Pass Rate**: {er.get('pass_rate', 0):.1%}\n"
                md += f"- **Duration**: {r.duration_seconds:.1f}s\n"
                return {"format": "markdown", "content": md}
            if format == "html":
                er = r.eval_result or {}
                from ..reporter.report import ReportGenerator

                html = ReportGenerator.to_html([], title=f"Result: {task_id}")
                return {"format": "html", "content": html}
            return {"format": "json", "content": r.eval_result}
    raise HTTPException(status_code=404, detail=f"Result for '{task_id}' not found")


@app.get("/api/v1/results/trend", response_model=list[TrendPoint])
async def get_trend(
    model: str | None = None,
    executor_key: str | None = None,
    level: str | None = None,
    limit: int = Query(50, ge=1, le=200),
):
    store = _get_store()
    records = store.query(model=model, executor_key=executor_key, level=level, limit=limit)
    return [
        TrendPoint(
            timestamp=r.timestamp[:19],
            metric_value=(r.eval_result or {}).get("metric_value", 0.0),
            model=r.model,
            executor_key=r.executor_key,
        )
        for r in records
    ]


@app.get("/api/v1/results/{task_id}/cases")
async def get_result_cases(
    task_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = None,
):
    store = _get_store()
    records = store.query(limit=1000)
    for r in records:
        if r.trace_id == task_id or r.task_id == task_id:
            er = r.eval_result or {}
            cases = er.get("cases", [])
            if status == "passed":
                cases = [c for c in cases if c.get("passed", False)]
            elif status == "failed":
                cases = [c for c in cases if not c.get("passed", True)]
            start = (page - 1) * page_size
            return {
                "task_id": task_id,
                "total": len(cases),
                "page": page,
                "cases": cases[start : start + page_size],
            }
    raise HTTPException(status_code=404, detail=f"Result for '{task_id}' not found")


# ── Quality Gates ───────────────────────────────────────────────────


@app.post("/api/v1/gates/check", response_model=GateCheckResponse)
async def check_gate(req: GateCheckRequest):
    from ..executors import register_all
    from ..orchestrator.gate_engine import GateEngine

    register_all()

    engine = GateEngine()
    engine.load_default_gates()

    store = _get_store()
    records = store.query(limit=1000)
    target = None
    for r in records:
        if r.trace_id == req.task_id or r.task_id == req.task_id:
            target = r
            break
    if not target:
        raise HTTPException(status_code=404, detail=f"Task '{req.task_id}' not found")

    er = target.eval_result or {}
    gates = engine.evaluate(
        executor_key=target.executor_key,
        metric_name=er.get("metric_name", ""),
        metric_value=er.get("metric_value", 0.0),
        level=target.level,
    )
    if req.gate_id:
        gates = [g for g in gates if g.gate_id == req.gate_id]
    if req.tier:
        gates = [g for g in gates if g.tier.value == req.tier]

    overall = all(g.passed for g in gates) if gates else True
    return GateCheckResponse(passed=overall, gates=[g.to_dict() for g in gates])


@app.get("/api/v1/gates")
async def list_gates(tier: str | None = None, level: str | None = None):
    from ..executors import register_all
    from ..orchestrator.gate_engine import GateEngine

    register_all()

    engine = GateEngine()
    engine.load_default_gates()
    gates = engine._adhoc_gates
    if tier:
        gates = [g for g in gates if g.tier.value == tier]
    if level:
        gates = [g for g in gates if g.level and g.level.value == level]
    return {"gates": [g.to_dict() for g in gates]}


@app.post("/api/v1/gates", status_code=201)
async def create_gate(req: GateRuleCreate):
    from ..core.models import QualityGate
    from ..orchestrator.gate_engine import GateEngine

    gate = QualityGate(
        gate_id=f"custom-{uuid.uuid4().hex[:6]}",
        name=req.name,
        tier=GateTier(req.tier),
        metric_name=req.metric_name,
        operator=req.operator,
        threshold=req.threshold,
        executor_key=req.executor_key,
        level=EvalLevel(req.level) if req.level else None,
    )
    engine = GateEngine()
    engine.load_default_gates()
    engine.add_gate(gate)
    return {"gate_id": gate.gate_id, "gate": gate.to_dict()}


_gate_approvals: dict[str, dict[str, Any]] = {}


@app.post("/api/v1/gates/{gate_id}/approve")
async def approve_gate(
    gate_id: str,
    req: GateApproveRequest,
    _user: str = Depends(require_permission(Permission.GATE_APPROVE)),
):
    _gate_approvals[gate_id] = {
        "gate_id": gate_id,
        "approver": req.approver,
        "remark": req.remark,
        "approved_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    return {"gate_id": gate_id, "approved": True, "approver": req.approver}


# ── System Management ───────────────────────────────────────────────


@app.get("/api/v1/system/health", response_model=HealthResponse)
async def health_check():
    store = _get_store()
    total = store.stats()["total"]
    active = sum(1 for v in _background_tasks.values() if v.get("status") == "running")
    return HealthResponse(
        status="ok",
        uptime_seconds=time.time() - _start_time,
        active_tasks=active,
        store_total=total,
    )


@app.get("/api/v1/system/resources")
async def system_resources():
    from ..engine.metal_monitor import MetalMonitor

    monitor = MetalMonitor()
    info = monitor.get_gpu_info()
    return {"gpu": info}


@app.get("/api/v1/system/audit-logs")
async def audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    action: str | None = None,
    actor: str | None = None,
):
    try:
        from ..storage.audit_store import AuditStore

        astore = AuditStore()
        result = astore.query(action=action, actor=actor, limit=page_size, offset=(page - 1) * page_size)
        stats = astore.stats()
        return {"total": stats["total"], "page": page, "items": result}
    except Exception:
        store = _get_store()
        records = store.query(limit=page_size * page)
        items = [
            {
                "trace_id": r.trace_id,
                "model": r.model,
                "executor_key": r.executor_key,
                "status": r.status.value,
                "timestamp": r.timestamp[:19],
            }
            for r in records[(page - 1) * page_size : page * page_size]
        ]
        return {"total": len(records), "page": page, "items": items}


@app.get("/api/v1/system/gpu")
async def gpu_stats():
    from .gpu_monitor import get_gpu_stats

    stats = await get_gpu_stats()
    return stats.to_dict()


@app.get("/api/v1/tasks/{task_id}/events")
async def task_events(task_id: str):
    from starlette.responses import StreamingResponse

    from .sse import get_progress_stream

    stream = get_progress_stream()
    return StreamingResponse(
        stream.subscribe(task_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Baselines ────────────────────────────────────────────────────────


class BaselineCreateRequest(BaseModel):
    name: str
    model: str
    executor_key: str
    level: str = "L1"
    metrics: dict[str, Any] = Field(default_factory=dict)


@app.post("/api/v1/baselines", status_code=201)
async def create_baseline(
    req: BaselineCreateRequest,
    _user: str = Depends(require_permission(Permission.BASELINE_MANAGE)),
):
    from ..core.models import EvalLevel
    from ..storage.baseline_store import BaselineStore

    store = BaselineStore()
    store.set_baseline(
        name=req.name,
        model=req.model,
        executor_key=req.executor_key,
        level=EvalLevel(req.level),
        metrics=req.metrics,
    )
    return {"name": req.name, "created": True}


@app.get("/api/v1/baselines")
async def list_baselines(model: str | None = None):
    from ..storage.baseline_store import BaselineStore

    store = BaselineStore()
    return {"baselines": store.list_baselines(model=model)}


@app.get("/api/v1/baselines/{name}")
async def get_baseline(name: str, model: str | None = None):
    from ..storage.baseline_store import BaselineStore

    store = BaselineStore()
    bl = store.get_baseline(name=name, model=model)
    if not bl:
        raise HTTPException(status_code=404, detail=f"Baseline '{name}' not found")
    return bl


@app.delete("/api/v1/baselines/{name}")
async def delete_baseline(name: str, _user: str = Depends(require_permission(Permission.BASELINE_MANAGE))):
    from ..storage.baseline_store import BaselineStore

    store = BaselineStore()
    store.delete_baseline(name=name)
    return {"deleted": True}


@app.post("/api/v1/baselines/{name}/diff")
async def diff_baseline(name: str, req: dict[str, Any]):
    from ..storage.baseline_store import BaselineStore

    store = BaselineStore()
    diff = store.diff(
        name=name,
        model=req.get("model", ""),
        executor_key=req.get("executor_key", ""),
        level=req.get("level", "L1"),
        current_metrics=req.get("current_metrics", {}),
    )
    return diff


@app.post("/api/v1/baselines/seed")
async def seed_baselines(
    overwrite: bool = False,
    _user: str = Depends(require_permission(Permission.BASELINE_MANAGE)),
):
    from ..storage.baseline_store import BaselineStore

    store = BaselineStore()
    created = store.seed_default_baselines(overwrite=overwrite)
    return {"seeded": created, "count": len(created)}


# ── Schedules ────────────────────────────────────────────────────────


class ScheduleCreateRequest(BaseModel):
    name: str
    cron: str
    model: str
    executor_key: str = "speed"
    level: str = "L1"
    params: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


@app.post("/api/v1/schedules", status_code=201)
async def create_schedule(
    req: ScheduleCreateRequest,
    _user: str = Depends(require_permission(Permission.SCHEDULE_MANAGE)),
):
    from ..orchestrator.scheduler_engine import SchedulerConfig, ScheduleStore

    store = ScheduleStore()
    cfg = SchedulerConfig(
        schedule_id=f"sched-{uuid.uuid4().hex[:8]}",
        name=req.name,
        cron=req.cron,
        model=req.model,
        executor_key=req.executor_key,
        level=req.level,
        params=req.params,
        enabled=req.enabled,
    )
    store.add(cfg)
    return {"schedule_id": cfg.schedule_id, "created": True}


@app.get("/api/v1/schedules")
async def list_schedules():
    from ..orchestrator.scheduler_engine import ScheduleStore

    store = ScheduleStore()
    return {"schedules": [vars(s) for s in store.list_schedules()]}


@app.put("/api/v1/schedules/{schedule_id}/toggle")
async def toggle_schedule(
    schedule_id: str,
    _user: str = Depends(require_permission(Permission.SCHEDULE_MANAGE)),
):
    from ..orchestrator.scheduler_engine import ScheduleStore

    store = ScheduleStore()
    cfg = store.get(schedule_id)
    if not cfg:
        raise HTTPException(status_code=404, detail="Schedule not found")
    store.toggle(schedule_id, enabled=not cfg.enabled)
    return {"schedule_id": schedule_id, "enabled": not cfg.enabled}


@app.delete("/api/v1/schedules/{schedule_id}")
async def delete_schedule(
    schedule_id: str,
    _user: str = Depends(require_permission(Permission.SCHEDULE_MANAGE)),
):
    from ..orchestrator.scheduler_engine import ScheduleStore

    store = ScheduleStore()
    store.delete(schedule_id)
    return {"deleted": True}


# ── Datasets ─────────────────────────────────────────────────────────


class DatasetCreateRequest(BaseModel):
    name: str
    items: list[dict[str, Any]] = Field(default_factory=list)
    description: str = ""
    format: str = "json"


@app.post("/api/v1/datasets", status_code=201)
async def create_dataset(
    req: DatasetCreateRequest,
    _user: str = Depends(require_permission(Permission.DATASET_MANAGE)),
):
    from ..storage.dataset_store import DatasetStore

    store = DatasetStore()
    ds_id = store.create(name=req.name, items=req.items, description=req.description, format=req.format)
    return {"dataset_id": ds_id, "created": True}


@app.get("/api/v1/datasets")
async def list_datasets():
    from ..storage.dataset_store import DatasetStore

    store = DatasetStore()
    return {"datasets": store.list_datasets()}


@app.get("/api/v1/datasets/{dataset_id}")
async def get_dataset(dataset_id: str):
    from ..storage.dataset_store import DatasetStore

    store = DatasetStore()
    ds = store.get(dataset_id)
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return ds


@app.delete("/api/v1/datasets/{dataset_id}")
async def delete_dataset(dataset_id: str, _user: str = Depends(require_permission(Permission.DATASET_MANAGE))):
    from ..storage.dataset_store import DatasetStore

    store = DatasetStore()
    store.delete(dataset_id)
    return {"deleted": True}


class DatasetLoadRequest(BaseModel):
    name: str
    path: str
    format: str
    description: str = ""


@app.post("/api/v1/datasets/load", status_code=201)
async def load_dataset_file(
    req: DatasetLoadRequest,
    _user: str = Depends(require_permission(Permission.DATASET_MANAGE)),
):
    from ..storage.dataset_store import SUPPORTED_FORMATS, DatasetStore

    if req.format not in SUPPORTED_FORMATS:
        raise HTTPException(
            status_code=400,
            detail=f"unsupported format '{req.format}'; supported: {', '.join(SUPPORTED_FORMATS)}",
        )
    store = DatasetStore()
    ds_id = store.load_dataset_file(req.path, req.format, req.name, req.description)
    if not ds_id:
        raise HTTPException(status_code=400, detail="load failed (see logs): bad path or format validation error")
    return {"dataset_id": ds_id, "loaded": True, "format": req.format}


# ── Judges ───────────────────────────────────────────────────────────


class JudgeCreateRequest(BaseModel):
    name: str
    model: str = "qwen3.5-9b"
    judge_type: str = "hybrid"
    weight: float = 0.5
    prompt_template: str = ""
    criteria: list[str] = Field(default_factory=list)
    rubric: str = ""
    score_range: tuple[int, int] = (1, 10)
    temperature: float = 0.3
    max_tokens: int = 256


@app.post("/api/v1/judges", status_code=201)
async def create_judge(req: JudgeCreateRequest):
    from ..core.judge_config import JudgeConfig, JudgeStore

    store = JudgeStore()
    cfg = JudgeConfig(
        name=req.name,
        model=req.model,
        judge_type=req.judge_type,
        weight=req.weight,
        prompt_template=req.prompt_template,
        criteria=req.criteria,
        rubric=req.rubric,
        score_range=tuple(float(x) for x in req.score_range),
        temperature=req.temperature,
        max_tokens=req.max_tokens,
    )
    store.save(req.name, cfg)
    return {"name": req.name, "created": True}


@app.get("/api/v1/judges")
async def list_judges():
    from ..core.judge_config import JudgeStore

    store = JudgeStore()
    names = store.list()
    judges = []
    for n in names:
        cfg = store.get(n)
        if cfg:
            judges.append(cfg.to_dict())
    return {"judges": judges}


@app.delete("/api/v1/judges/{name}")
async def delete_judge(name: str):
    from ..core.judge_config import JudgeStore

    store = JudgeStore()
    deleted = store.delete(name)
    return {"deleted": deleted}


# ── Approvals ────────────────────────────────────────────────────────


class ApprovalCreateRequest(BaseModel):
    gate_id: str
    gate_name: str
    metric_name: str
    metric_value: float
    threshold: float
    requester: str


@app.post("/api/v1/approvals", status_code=201)
async def create_approval(req: ApprovalCreateRequest):
    from ..orchestrator.approval_workflow import ApprovalStore

    store = ApprovalStore()
    req_id = store.create_request(
        gate_id=req.gate_id,
        gate_name=req.gate_name,
        metric_name=req.metric_name,
        metric_value=req.metric_value,
        threshold=req.threshold,
        requester=req.requester,
    )
    return {"request_id": req_id, "created": True}


@app.get("/api/v1/approvals")
async def list_approvals(status: str | None = None):
    from ..orchestrator.approval_workflow import ApprovalStore

    store = ApprovalStore()
    if status == "pending":
        return {"approvals": store.list_pending()}
    return {"approvals": store.list_all()}


@app.put("/api/v1/approvals/{request_id}/approve")
async def approve_approval(request_id: str, req: GateApproveRequest):
    from ..orchestrator.approval_workflow import ApprovalStore

    store = ApprovalStore()
    store.approve(request_id, approver=req.approver, reason=req.remark)
    return {"request_id": request_id, "status": "approved"}


@app.put("/api/v1/approvals/{request_id}/reject")
async def reject_approval(request_id: str, req: GateApproveRequest):
    from ..orchestrator.approval_workflow import ApprovalStore

    store = ApprovalStore()
    store.reject(request_id, approver=req.approver, reason=req.remark)
    return {"request_id": request_id, "status": "rejected"}


# ── Backup ───────────────────────────────────────────────────────────


@app.post("/api/v1/system/backup")
async def create_backup(
    label: str = Query("manual"),
    _user: str = Depends(require_permission(Permission.SYSTEM_ADMIN)),
):
    from ..storage.backup import DataBackup

    backup = DataBackup()
    path = backup.backup(label=label)
    return {"label": label, "path": path}


@app.get("/api/v1/system/backups")
async def list_backups():
    from ..storage.backup import DataBackup

    backup = DataBackup()
    return {"backups": backup.list_backups()}


@app.post("/api/v1/system/restore")
async def restore_backup(
    label: str = Query(...),
    db_name: str | None = None,
    _user: str = Depends(require_permission(Permission.SYSTEM_ADMIN)),
):
    from ..storage.backup import DataBackup

    backup = DataBackup()
    backup.restore(label=label, db_name=db_name)
    return {"label": label, "restored": True}
