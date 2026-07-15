"""Fusion-Bench CLI — command-line interface for running benchmarks and tuning.

Usage:
    fusion-bench list-tasks                   # List available tasks
    fusion-bench run mmlu --model qwen3.5-9b  # Run a single task
    fusion-bench tune --model qwen3.5-9b      # Auto-tune parameters
    fusion-bench compare --models m1,m2       # Compare models
    fusion-bench quant --model qwen3.5-9b     # Quantization comparison
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


def main():
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

    # run
    run_parser = subparsers.add_parser("run", help="Run a benchmark task")
    run_parser.add_argument("task", help="Task name (e.g., mmlu, gsm8k)")
    run_parser.add_argument("--max-samples", type=int, default=0, help="Max samples to evaluate")
    run_parser.add_argument("--output", default="", help="Output file path (JSON)")

    # tune
    tune_parser = subparsers.add_parser("tune", help="Auto-tune model parameters")
    tune_parser.add_argument("--max-combinations", type=int, default=12, help="Max parameter combinations")
    tune_parser.add_argument("--output", default="", help="Output file path (JSON)")

    # compare
    compare_parser = subparsers.add_parser("compare", help="Compare multiple models")
    compare_parser.add_argument("--models", required=True, help="Comma-separated model names")
    compare_parser.add_argument("--tasks", default="mmlu,gsm8k", help="Comma-separated task names")
    compare_parser.add_argument("--output", default="", help="Output file path (JSON)")

    # speed
    speed_parser = subparsers.add_parser("speed", help="Benchmark model speed")
    speed_parser.add_argument("--runs", type=int, default=3, help="Number of runs")
    speed_parser.add_argument("--output", default="", help="Output file path (JSON)")

    # quant
    quant_parser = subparsers.add_parser("quant", help="Compare quantization levels")
    quant_parser.add_argument("--levels", default="mxfp4,mxfp8,mixed_3_4",
                              help="Comma-separated quant levels")
    quant_parser.add_argument("--output", default="", help="Output file path (JSON)")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    if args.command == "list-tasks":
        cmd_list_tasks(args)
    elif args.command == "run":
        asyncio.run(cmd_run(args))
    elif args.command == "tune":
        asyncio.run(cmd_tune(args))
    elif args.command == "compare":
        asyncio.run(cmd_compare(args))
    elif args.command == "speed":
        asyncio.run(cmd_speed(args))
    elif args.command == "quant":
        asyncio.run(cmd_quant(args))


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

    # Print comparison table
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
    # Print comparison table
    print(f"\n{'Quant':<20} {'Speed (tok/s)':<15} {'Memory (MB)':<15}")
    print("-" * 50)
    for r in results:
        print(f"{r['quant']:<20} {r['speed']:<15.1f} {r['memory']:<15.0f}")
    if args.output:
        Path(args.output).write_text(
            json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8"
        )


if __name__ == "__main__":
    main()