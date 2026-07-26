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
from .reporter.report import ReportGenerator


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
    parser.add_argument("--mlx-url", default="http://localhost:11434/v1",
                        help="fusion-mlx API URL (default: http://localhost:11434/v1)")
    parser.add_argument("--model", default="qwen3.5-9b",
                        help="Model name (default: qwen3.5-9b)")

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
    suite_parser.add_argument("--tier", default="experimental",
                               choices=["experimental", "business", "production"],
                               help="Quality gate tier")
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
    quant_parser.add_argument("--levels", default="mxfp4,mxfp8,mixed_3_4",
                              help="Comma-separated quant levels")
    quant_parser.add_argument("--output", default="", help="Output file path (JSON)")

    # security (NEW)
    sec_parser = subparsers.add_parser("security", help="Run security probes on model")
    sec_parser.add_argument("--probe-set", default="injection",
                             choices=["injection", "harmful", "pii"],
                             help="Probe set to use")
    sec_parser.add_argument("--output", default="", help="Output file path (JSON)")

    # compare
    compare_parser = subparsers.add_parser("compare", help="Compare multiple models")
    compare_parser.add_argument("--models", required=True, help="Comma-separated model names")
    compare_parser.add_argument("--tasks", default="mmlu,gsm8k", help="Comma-separated task names")
    compare_parser.add_argument("--output", default="", help="Output file path (JSON)")

    # gates (NEW)
    gates_parser = subparsers.add_parser("gates", help="Show quality gate thresholds")
    gates_parser.add_argument("--tier", default="", choices=["", "experimental", "business", "production"],
                               help="Filter by tier")

    # traces (NEW)
    traces_parser = subparsers.add_parser("traces", help="Query trace store")
    traces_parser.add_argument("--model", default="", help="Filter by model")
    traces_parser.add_argument("--executor", default="", help="Filter by executor")
    traces_parser.add_argument("--level", default="", help="Filter by level")
    traces_parser.add_argument("--limit", type=int, default=20, help="Max results")

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
    from .orchestrator.pipeline import Pipeline
    from .orchestrator.gate_engine import GateEngine
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
            print(f"  {symbol} [{g.tier.value:12s}] {g.gate_name}: "
                  f"{g.metric_name}={g.metric_value:.4f} {g.threshold} → "
                  f"{'PASS' if g.passed else 'FAIL'}")

    if args.output:
        Path(args.output).write_text(
            json.dumps(result.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
        )
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
        Path(args.output).write_text(
            json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"\nResults saved to {args.output}")


async def cmd_tune(args):
    """Auto-tune model parameters."""
    print(f"Tuning model '{args.model}'...")
    tuner = ParameterTuner(mlx_base_url=args.mlx_url)
    result = await tuner.tune(args.model, max_combinations=args.max_combinations)
    print(f"\nBest config: {json.dumps(result.best_config, indent=2)}")
    print(f"Best speed: {result.best_speed:.1f} tok/s")
    print(f"\nTop 3 configs:")
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
        Path(args.output).write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"\nResults saved to {args.output}")


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
        Path(args.output).write_text(
            json.dumps(all_results, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"\nResults saved to {args.output}")


async def cmd_speed(args):
    """Benchmark model speed."""
    runner = BenchmarkRunner(mlx_base_url=args.mlx_url)
    print(f"Benchmarking speed for '{args.model}' ({args.runs} runs)...")
    results = await runner.benchmark(args.model, runs=args.runs)
    for r in results:
        print(f"\n  Decode speed: {r.metrics.decode_speed:.1f} tok/s")
        print(f"  Prefill speed: {r.metrics.prefill_speed:.1f} tok/s")
        print(f"  Peak memory: {r.metrics.peak_memory_mb:.0f} MB")
        print(f"  Total time: {r.metrics.total_time:.2f}s")
    if args.output:
        data = [r.metrics.to_dict() for r in results]
        Path(args.output).write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )


async def cmd_quant(args):
    """Compare quantization levels."""
    levels = [l.strip() for l in args.levels.split(",")]
    print(f"Comparing quantization levels: {levels}")
    runner = BenchmarkRunner(mlx_base_url=args.mlx_url)
    results = []
    for level in levels:
        model_name = f"{args.model}-{level}"
        print(f"  Testing {model_name}...")
        r = await runner.benchmark(model_name, runs=2)
        if r:
            results.append({
                "model": model_name,
                "quant": level,
                "speed": r[0].metrics.decode_speed,
                "memory": r[0].metrics.peak_memory_mb,
            })
    print(f"\n{'Quant':<20} {'Speed (tok/s)':<15} {'Memory (MB)':<15}")
    print("-" * 50)
    for r in results:
        print(f"{r['quant']:<20} {r['speed']:<15.1f} {r['memory']:<15.0f}")
    if args.output:
        Path(args.output).write_text(
            json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8"
        )


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
        Path(args.output).write_text(
            json.dumps(result.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
        )
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
        print(f"{g.gate_id:<20} {g.name:<25} {g.tier.value:<14} {g.metric_name:<20} "
              f"{g.operator} {g.threshold}")


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
            print(f"{r.trace_id:<20} {r.model:<20} {r.executor_key:<15} "
                  f"{r.status.value:<10} {r.duration_seconds:<10.1f} {r.timestamp[:19]}")
    finally:
        store.close()


if __name__ == "__main__":
    main()
