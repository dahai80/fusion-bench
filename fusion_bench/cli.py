"""Fusion-Bench CLI v2 — plugin-based benchmarking with quality gates.

Usage:
    fusion-bench list-tasks                   # List available tasks
    fusion-bench list-suites                  # List benchmark suites
    fusion-bench list-executors               # List registered executors
    fusion-bench run mmlu --model qwen3.5-9b  # Run a single task
    fusion-bench suite l1-quick --model ...   # Run a suite with quality gates
    fusion-bench speed --model qwen3.5-9b     # Speed benchmark
    fusion-bench tune --model qwen3.5-9b      # Auto-tune parameters
    fusion-bench quant --model qwen3.5-9b     # Quantization comparison
    fusion-bench security --model qwen3.5-9b  # Security probes
    fusion-bench gates                        # Show quality gate thresholds
    fusion-bench traces                       # Query trace store
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from .engine.benchmark import BenchmarkRunner
from .engine.task_runner import LMEvalTaskRunner
from .optimizer.tuner import ParameterTuner


def _bootstrap():
    """Register all plugins and load defaults."""
    from .executors import register_all

    register_all()


def main():
    _bootstrap()

    parser = argparse.ArgumentParser(
        description="Fusion-Bench — MLX model benchmarking and auto-tuning",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--mlx-url",
        default="http://localhost:11432/v1",
        help="fusion-mlx API URL (default: http://localhost:11432/v1)",
    )
    parser.add_argument("--model", default="qwen3.5-9b", help="Model name (default: qwen3.5-9b)")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # list-tasks
    list_parser = subparsers.add_parser("list-tasks", help="List available evaluation tasks")
    list_parser.add_argument("--pattern", default="", help="Filter tasks by pattern")

    # list-suites
    subparsers.add_parser("list-suites", help="List available benchmark suites")

    # list-executors
    subparsers.add_parser("list-executors", help="List registered executor plugins")

    # run
    run_parser = subparsers.add_parser("run", help="Run a benchmark task")
    run_parser.add_argument("task", help="Task name (e.g., mmlu, gsm8k)")
    run_parser.add_argument("--max-samples", type=int, default=0, help="Max samples to evaluate")
    run_parser.add_argument("--output", default="", help="Output file path (JSON)")

    # suite (NEW)
    suite_parser = subparsers.add_parser("suite", help="Run a benchmark suite with quality gates")
    suite_parser.add_argument("suite_name", help="Suite name (e.g., l1-quick, l1-full, l3-security)")
    suite_parser.add_argument("--level", default="L1", help="Evaluation level (L1/L2/L3/L4)")
    suite_parser.add_argument(
        "--tier",
        default="experimental",
        choices=["experimental", "business", "production"],
        help="Quality gate tier",
    )
    suite_parser.add_argument("--output", default="", help="Output file path (JSON)")

    # speed
    speed_parser = subparsers.add_parser("speed", help="Benchmark model speed")
    speed_parser.add_argument("--runs", type=int, default=3, help="Number of runs")
    speed_parser.add_argument("--output", default="", help="Output file path (JSON)")

    # tune
    tune_parser = subparsers.add_parser("tune", help="Auto-tune model parameters")
    tune_parser.add_argument("--max-combinations", type=int, default=12, help="Max parameter combinations")
    tune_parser.add_argument("--output", default="", help="Output file path (JSON)")

    # quant
    quant_parser = subparsers.add_parser("quant", help="Compare quantization levels")
    quant_parser.add_argument("--levels", default="mxfp4,mxfp8,mixed_3_4", help="Comma-separated quant levels")
    quant_parser.add_argument("--output", default="", help="Output file path (JSON)")

    # security (NEW)
    sec_parser = subparsers.add_parser("security", help="Run security probes on model")
    sec_parser.add_argument(
        "--probe-set",
        default="injection",
        choices=["injection", "harmful", "pii"],
        help="Probe set to use",
    )
    sec_parser.add_argument("--output", default="", help="Output file path (JSON)")

    # compare
    compare_parser = subparsers.add_parser("compare", help="Compare multiple models")
    compare_parser.add_argument("--models", required=True, help="Comma-separated model names")
    compare_parser.add_argument("--tasks", default="mmlu,gsm8k", help="Comma-separated task names")
    compare_parser.add_argument("--output", default="", help="Output file path (JSON)")

    # gates (NEW)
    gates_parser = subparsers.add_parser("gates", help="Show quality gate thresholds")
    gates_parser.add_argument(
        "--tier",
        default="",
        choices=["", "experimental", "business", "production"],
        help="Filter by tier",
    )

    # traces (NEW)
    traces_parser = subparsers.add_parser("traces", help="Query trace store")
    traces_parser.add_argument("--model", default="", help="Filter by model")
    traces_parser.add_argument("--executor", default="", help="Filter by executor")
    traces_parser.add_argument("--level", default="", help="Filter by level")
    traces_parser.add_argument("--limit", type=int, default=20, help="Max results")

    # serve (API server)
    serve_parser = subparsers.add_parser("serve", help="Start REST API server")
    serve_parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    serve_parser.add_argument("--port", type=int, default=11450, help="Bind port (default: 11450)")
    serve_parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    serve_parser.add_argument("--ssl-certfile", default="", help="TLS certificate file")
    serve_parser.add_argument("--ssl-keyfile", default="", help="TLS private key file")
    serve_parser.add_argument(
        "--tls-enforce",
        action="store_true",
        help="Reject non-TLS connections (redirect HTTP to HTTPS)",
    )

    # bench-site
    benchsite_parser = subparsers.add_parser("bench-site", help="Manage bench-site web UI")
    benchsite_parser.add_argument(
        "action",
        choices=["dev", "build", "deploy", "stats"],
        help="Action: dev/build/deploy/stats",
    )
    benchsite_parser.add_argument("--port", type=int, default=11461, help="Dev server port (default: 11461)")
    benchsite_parser.add_argument("--skip-build", action="store_true", help="Deploy: skip build step")
    benchsite_parser.add_argument("--skip-restart", action="store_true", help="Deploy: skip service restart")

    # baseline
    baseline_parser = subparsers.add_parser("baseline", help="Manage named baselines")
    baseline_parser.add_argument("action", choices=["set", "list", "diff", "delete"], help="Action")
    baseline_parser.add_argument("--name", default="", help="Baseline name")
    baseline_parser.add_argument("--model", default="", help="Model name")
    baseline_parser.add_argument("--executor", default="speed", help="Executor key")
    baseline_parser.add_argument("--level", default="L1", help="Eval level")

    # schedule
    schedule_parser = subparsers.add_parser("schedule", help="Manage cron schedules")
    schedule_parser.add_argument("action", choices=["list", "add", "toggle", "delete"], help="Action")
    schedule_parser.add_argument("--name", default="", help="Schedule name")
    schedule_parser.add_argument("--cron", default="0 */6 * * *", help="Cron expression")
    schedule_parser.add_argument("--id", default="", help="Schedule ID for toggle/delete")

    # dataset
    dataset_parser = subparsers.add_parser("dataset", help="Manage custom datasets")
    dataset_parser.add_argument("action", choices=["list", "create", "delete"], help="Action")
    dataset_parser.add_argument("--name", default="", help="Dataset name")
    dataset_parser.add_argument("--id", default="", help="Dataset ID for delete")

    # backup
    backup_parser = subparsers.add_parser("backup", help="Backup/restore databases")
    backup_parser.add_argument("action", choices=["create", "list", "restore"], help="Action")
    backup_parser.add_argument("--label", default="manual", help="Backup label")
    backup_parser.add_argument("--db", default=None, help="Specific DB name for restore")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    dispatch = {
        "list-tasks": lambda: cmd_list_tasks(args),
        "list-suites": lambda: cmd_list_suites(args),
        "list-executors": lambda: cmd_list_executors(args),
        "run": lambda: asyncio.run(cmd_run(args)),
        "suite": lambda: asyncio.run(cmd_suite(args)),
        "speed": lambda: asyncio.run(cmd_speed(args)),
        "tune": lambda: asyncio.run(cmd_tune(args)),
        "quant": lambda: asyncio.run(cmd_quant(args)),
        "security": lambda: asyncio.run(cmd_security(args)),
        "compare": lambda: asyncio.run(cmd_compare(args)),
        "gates": lambda: cmd_gates(args),
        "traces": lambda: cmd_traces(args),
        "serve": lambda: cmd_serve(args),
        "bench-site": lambda: cmd_bench_site(args),
        "baseline": lambda: cmd_baseline(args),
        "schedule": lambda: cmd_schedule(args),
        "dataset": lambda: cmd_dataset(args),
        "backup": lambda: cmd_backup(args),
    }

    handler = dispatch.get(args.command)
    if handler:
        handler()
    else:
        parser.print_help()


def cmd_list_tasks(args):
    """List available evaluation tasks."""
    runner = LMEvalTaskRunner(mlx_base_url=args.mlx_url)
    tasks = runner.list_tasks()
    if args.pattern:
        tasks = [t for t in tasks if args.pattern.lower() in t["name"].lower()]
    if not tasks:
        print("No tasks found. Make sure lm-evaluation-harness is installed.")
        return
    print(f"\n{'Task Name':<30} {'Group':<25} {'Fewshot':<8} {'Dataset'}")
    print("-" * 90)
    for t in sorted(tasks, key=lambda x: x["name"]):
        print(f"{t['name']:<30} {t['group']:<25} {t['num_fewshot']:<8} {t['dataset']}")
    print(f"\nTotal: {len(tasks)} tasks")


def cmd_list_suites(args):
    """List available benchmark suites."""
    from .orchestrator.scheduler import Scheduler

    scheduler = Scheduler()
    scheduler.load_default_suites()

    for name in scheduler.list_suites():
        tasks = scheduler.get_suite(name)
        print(f"\n  {name} ({len(tasks)} tasks):")
        for t in tasks:
            print(f"    - {t.task_id}: {t.name} [{t.level.value}] via {t.executor_key}")


def cmd_list_executors(args):
    """List registered executor plugins."""
    from .core.registry import executor_registry

    print("\nRegistered Executors:")
    for key in executor_registry.list_keys():
        cls = executor_registry.get(key)
        if cls:
            instance = cls()
            available = "✓" if instance.is_available() else "✗"
            print(f"  {available} {key:20s} type={instance.executor_type.value}")


async def cmd_suite(args):
    """Run a benchmark suite with quality gates."""
    from .orchestrator.gate_engine import GateEngine
    from .orchestrator.pipeline import Pipeline
    from .orchestrator.scheduler import Scheduler
    from .storage.trace_store import TraceStore

    scheduler = Scheduler()
    scheduler.load_default_suites()

    gate_engine = GateEngine()
    gate_engine.load_default_gates()

    store = TraceStore()

    try:
        task_configs = scheduler.suite_to_task_configs(args.suite_name)
    except KeyError as e:
        print(f"Error: {e}")
        return

    pipeline = Pipeline(gate_engine=gate_engine, trace_callback=store.insert)

    print(f"Running suite '{args.suite_name}' with model '{args.model}'...")
    result = await pipeline.run_suite(
        model=args.model,
        tasks=task_configs,
        level=args.level,
    )

    print(f"\nSuite: {result.suite_id}")
    print(f"Model: {result.model}")
    print(f"Level: {result.level.value}")
    print(f"Duration: {result.duration_seconds:.1f}s")
    print(f"Overall: {'PASS ✓' if result.overall_passed else 'FAIL ✗'}")

    print(f"\nResults ({len(result.results)} tasks):")
    for r in result.results:
        executor = r.get("executor_key", "?")
        metric = r.get("metric_name", "?")
        value = r.get("metric_value", 0)
        errors = r.get("errors", [])
        status = "✓" if not errors else "✗"
        print(f"  {status} {executor:20s} {metric}={value:.4f}")

    if result.gate_results:
        print(f"\nQuality Gates ({len(result.gate_results)}):")
        for g in result.gate_results:
            symbol = "✓" if g.passed else "✗"
            print(
                f"  {symbol} [{g.tier.value:12s}] {g.gate_name}: "
                f"{g.metric_name}={g.metric_value:.4f} {g.threshold} → "
                f"{'PASS' if g.passed else 'FAIL'}"
            )

    if args.output:
        Path(args.output).write_text(json.dumps(result.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nResults saved to {args.output}")

    store.close()


async def cmd_run(args):
    """Run a single benchmark task."""
    print(f"Running task '{args.task}' with model '{args.model}'...")
    runner = LMEvalTaskRunner(
        model=args.model,
        mlx_base_url=args.mlx_url,
        max_samples=args.max_samples,
    )
    result = await runner.run_task(args.task)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if args.output:
        Path(args.output).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nResults saved to {args.output}")


async def cmd_tune(args):
    """Auto-tune model parameters."""
    print(f"Tuning model '{args.model}'...")
    tuner = ParameterTuner(mlx_base_url=args.mlx_url)
    try:
        result = await tuner.tune(args.model, max_combinations=args.max_combinations)
        print(f"\nBest config: {json.dumps(result.best_config, indent=2)}")
        print(f"Best speed: {result.best_speed:.1f} tok/s")
        print("\nTop 3 configs:")
        for i, cfg in enumerate(result.top3_configs, 1):
            print(f"  {i}. {cfg}")
        if args.output:
            data = {
                "model": args.model,
                "best_config": result.best_config,
                "best_speed": result.best_speed,
                "top3_configs": result.top3_configs,
                "memory_saving_config": result.memory_saving_config,
                "balanced_config": result.balanced_config,
            }
            Path(args.output).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"\nResults saved to {args.output}")
    finally:
        await tuner.runner.close()


async def cmd_compare(args):
    """Compare multiple models."""
    models = [m.strip() for m in args.models.split(",")]
    tasks = [t.strip() for t in args.tasks.split(",")]
    print(f"Comparing models: {models}")
    print(f"Tasks: {tasks}")
    print()

    all_results = []
    for model in models:
        print(f"Benchmarking {model}...")
        runner = LMEvalTaskRunner(model=model, mlx_base_url=args.mlx_url)
        results = await runner.run_benchmark(tasks)
        all_results.append({"model": model, "results": results})

    print(f"\n{'Model':<20}", end="")
    for task in tasks:
        print(f"{task:<15}", end="")
    print()
    print("-" * (20 + 15 * len(tasks)))
    for entry in all_results:
        print(f"{entry['model']:<20}", end="")
        for r in entry["results"]:
            acc = r.get("metrics", {}).get("accuracy", 0)
            print(f"{acc:<15.2%}", end="")
        print()

    if args.output:
        Path(args.output).write_text(json.dumps(all_results, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nResults saved to {args.output}")


async def cmd_speed(args):
    """Benchmark model speed."""
    runner = BenchmarkRunner(mlx_base_url=args.mlx_url)
    try:
        print(f"Benchmarking speed for '{args.model}' ({args.runs} runs)...")
        results = await runner.benchmark(args.model, runs=args.runs)
        for r in results:
            print(f"\n  Decode speed: {r.metrics.decode_speed:.1f} tok/s")
            print(f"  Prefill speed: {r.metrics.prefill_speed:.1f} tok/s")
            print(f"  Peak memory: {r.metrics.peak_memory_mb:.0f} MB")
            print(f"  Total time: {r.metrics.total_time:.2f}s")
        if args.output:
            data = [r.metrics.to_dict() for r in results]
            Path(args.output).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    finally:
        await runner.close()


async def cmd_quant(args):
    """Compare quantization levels."""
    levels = [lv.strip() for lv in args.levels.split(",")]
    print(f"Comparing quantization levels: {levels}")
    runner = BenchmarkRunner(mlx_base_url=args.mlx_url)
    results = []
    try:
        for level in levels:
            model_name = f"{args.model}-{level}"
            print(f"  Testing {model_name}...")
            r = await runner.benchmark(model_name, runs=2)
            if r:
                results.append(
                    {
                        "model": model_name,
                        "quant": level,
                        "speed": r[0].metrics.decode_speed,
                        "memory": r[0].metrics.peak_memory_mb,
                    }
                )
        print(f"\n{'Quant':<20} {'Speed (tok/s)':<15} {'Memory (MB)':<15}")
        print("-" * 50)
        for r in results:
            print(f"{r['quant']:<20} {r['speed']:<15.1f} {r['memory']:<15.0f}")
        if args.output:
            Path(args.output).write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    finally:
        await runner.close()


async def cmd_security(args):
    """Run security probes on model."""
    from .core.plugin_base import TaskConfig
    from .executors.security_executor import SecurityExecutor

    executor = SecurityExecutor(mlx_base_url=args.mlx_url)
    config = TaskConfig(
        task_id=f"security-{args.probe_set}",
        model=args.model,
        executor_key="security",
        params={"probe_set": args.probe_set},
    )
    print(f"Running security probes ({args.probe_set}) on '{args.model}'...")
    result = await executor.run(config)

    print(f"\nSafety rate: {result.metric_value:.1%}")
    print(f"Probes: {len(result.cases)} total, {sum(1 for c in result.cases if c.passed)} safe")
    for c in result.cases:
        symbol = "✓" if c.passed else "✗"
        print(f"  {symbol} {c.input_text[:60]}... → {c.actual[:40]}")

    if args.output:
        Path(args.output).write_text(json.dumps(result.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nResults saved to {args.output}")


def cmd_gates(args):
    """Show quality gate thresholds."""
    from .orchestrator.gate_engine import GateEngine

    engine = GateEngine()
    engine.load_default_gates()

    gates = engine._adhoc_gates
    if args.tier:
        from .core.models import GateTier

        tier = GateTier(args.tier)
        gates = [g for g in gates if g.tier == tier]

    print("\nQuality Gates:")
    print(f"{'ID':<20} {'Name':<25} {'Tier':<14} {'Metric':<20} {'Rule'}")
    print("-" * 95)
    for g in sorted(gates, key=lambda x: (x.tier.value, x.metric_name)):
        print(f"{g.gate_id:<20} {g.name:<25} {g.tier.value:<14} {g.metric_name:<20} {g.operator} {g.threshold}")


def cmd_traces(args):
    """Query trace store."""
    from .storage.trace_store import TraceStore

    store = TraceStore()
    try:
        records = store.query(
            model=args.model or None,
            executor_key=args.executor or None,
            level=args.level or None,
            limit=args.limit,
        )
        if not records:
            print("No traces found.")
            return
        print(f"\n{'Trace ID':<20} {'Model':<20} {'Executor':<15} {'Status':<10} {'Duration':<10} {'Time'}")
        print("-" * 95)
        for r in records:
            print(
                f"{r.trace_id:<20} {r.model:<20} {r.executor_key:<15} "
                f"{r.status.value:<10} {r.duration_seconds:<10.1f} {r.timestamp[:19]}"
            )
    finally:
        store.close()


def cmd_serve(args):
    import uvicorn

    ssl_kwargs = {}
    if args.ssl_certfile and args.ssl_keyfile:
        ssl_kwargs["ssl_certfile"] = args.ssl_certfile
        ssl_kwargs["ssl_keyfile"] = args.ssl_keyfile
        print(f"TLS enabled: cert={args.ssl_certfile}")
    if args.tls_enforce:
        import os

        os.environ["FUSION_BENCH_TLS_ENFORCE"] = "1"
        if not args.ssl_certfile or not args.ssl_keyfile:
            print("WARNING: --tls-enforce set but no TLS certificates provided. HTTP requests will be rejected.")
    print(f"Starting Fusion-Bench API server on {args.host}:{args.port}...")
    uvicorn.run(
        "fusion_bench.api.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        **ssl_kwargs,
    )


def cmd_bench_site(args):
    """Manage bench-site web UI (dev/build/deploy/stats)."""
    import subprocess

    bench_site_dir = Path(__file__).resolve().parent.parent / "bench-site"

    if not bench_site_dir.exists():
        print(f"Error: bench-site directory not found at {bench_site_dir}")
        sys.exit(1)

    if args.action == "dev":
        port_args = ["--port", str(args.port)]
        print(f"Starting bench-site dev server on port {args.port}...")
        print(f"  cd {bench_site_dir} && npm run dev -- --port {args.port}")
        subprocess.run(["npm", "run", "dev", "--", *port_args], cwd=str(bench_site_dir))

    elif args.action == "build":
        print("Building bench-site for production...")
        subprocess.run(["npm", "run", "build"], cwd=str(bench_site_dir), check=True)
        print("Build completed successfully.")

    elif args.action == "deploy":
        deploy_args = []
        if args.skip_build:
            deploy_args.append("--skip-build")
        if args.skip_restart:
            deploy_args.append("--skip-restart")
        print("Deploying bench-site to production...")
        subprocess.run(["bash", "./deploy.sh", *deploy_args], cwd=str(bench_site_dir), check=True)

    elif args.action == "stats":
        from .reporter.bench_site_db import BenchSiteDB

        db = BenchSiteDB()
        try:
            s = db.stats()
            print("\nBench-Site Database Stats:")
            print(f"  Database path:  {s['database_path']}")
            print(f"  Total entries:  {s['total_entries']}")
            print(f"  Unique models:  {s['unique_models']}")
            print(f"  Unique chips:   {s['unique_chips']}")
        finally:
            db.close()


def cmd_baseline(args):
    from .core.models import EvalLevel
    from .storage.baseline_store import BaselineStore

    store = BaselineStore()
    try:
        if args.action == "list":
            baselines = store.list_baselines(model=args.model or None)
            if not baselines:
                print("No baselines found.")
                return
            for bl in baselines:
                print(
                    f"  {bl['name']:<20} model={bl.get('model', '')} level={bl.get('level', '')} metrics={bl.get('metrics', {})}"
                )
        elif args.action == "set":
            if not args.name:
                print("Error: --name required for set")
                return
            store.set_baseline(
                name=args.name,
                model=args.model,
                executor_key=args.executor,
                level=EvalLevel(args.level),
                metrics={},
            )
            print(f"Baseline '{args.name}' set for model={args.model}")
        elif args.action == "diff":
            if not args.name:
                print("Error: --name required for diff")
                return
            diff = store.diff(
                name=args.name,
                model=args.model,
                executor_key=args.executor,
                level=args.level,
                current_metrics={},
            )
            for metric, info in diff.get("diffs", {}).items():
                print(f"  {metric}: {info.get('delta', 'N/A')} [{info.get('direction', 'N/A')}]")
        elif args.action == "delete":
            if not args.name:
                print("Error: --name required for delete")
                return
            store.delete_baseline(name=args.name)
            print(f"Baseline '{args.name}' deleted.")
    finally:
        pass


def cmd_schedule(args):
    from .orchestrator.scheduler_engine import SchedulerConfig, ScheduleStore

    store = ScheduleStore()
    try:
        if args.action == "list":
            schedules = store.list_schedules()
            if not schedules:
                print("No schedules found.")
                return
            for s in schedules:
                status = "ON" if s.enabled else "OFF"
                print(f"  [{status}] {s.schedule_id:<16} {s.name:<20} cron={s.cron} model={s.model}")
        elif args.action == "add":
            if not args.name:
                print("Error: --name required for add")
                return
            cfg = SchedulerConfig(
                schedule_id=f"sched-{id(args):x}",
                name=args.name,
                cron=args.cron,
                model=args.model,
                executor_key="speed",
                level="L1",
                params={},
                enabled=True,
            )
            store.add(cfg)
            print(f"Schedule '{args.name}' added: {args.cron}")
        elif args.action == "toggle":
            if not args.id:
                print("Error: --id required for toggle")
                return
            cfg = store.get(args.id)
            if cfg:
                store.toggle(args.id, enabled=not cfg.enabled)
                print(f"Schedule {args.id} toggled to {'ON' if not cfg.enabled else 'OFF'}")
            else:
                print(f"Schedule {args.id} not found.")
        elif args.action == "delete":
            if not args.id:
                print("Error: --id required for delete")
                return
            store.delete(args.id)
            print(f"Schedule {args.id} deleted.")
    finally:
        pass


def cmd_dataset(args):
    from .storage.dataset_store import DatasetStore

    store = DatasetStore()
    try:
        if args.action == "list":
            datasets = store.list_datasets()
            if not datasets:
                print("No datasets found.")
                return
            for ds in datasets:
                print(f"  {ds['id']:<16} {ds['name']:<20} items={ds.get('item_count', 0)}")
        elif args.action == "create":
            if not args.name:
                print("Error: --name required for create")
                return
            ds_id = store.create(name=args.name, items=[], description="", format="json")
            print(f"Dataset '{args.name}' created: {ds_id}")
        elif args.action == "delete":
            if not args.id:
                print("Error: --id required for delete")
                return
            store.delete(args.id)
            print(f"Dataset {args.id} deleted.")
    finally:
        pass


def cmd_backup(args):
    from .storage.backup import DataBackup

    backup = DataBackup()
    if args.action == "create":
        path = backup.backup(label=args.label)
        print(f"Backup created: {path}")
    elif args.action == "list":
        backups = backup.list_backups()
        if not backups:
            print("No backups found.")
            return
        for b in backups:
            print(f"  {b['label']:<20} path={b['path']}")
    elif args.action == "restore":
        backup.restore(label=args.label, db_name=args.db)
        print(f"Restored from backup: {args.label}")


if __name__ == "__main__":
    main()
