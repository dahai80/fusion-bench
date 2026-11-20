"""Orchestrator + report writer for the comparison suite (issue #53).

`run_comparison(metrics=..., smoke=...)` executes the selected metric arms and
writes benchmarks/results/compare-suite/report.{json,md}. LLM-backed arms
(completion/tokens) call local fusion-mlx only; deterministic arms (hitl,
compaction, dag, simplicity) need no model.
"""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

ALL_METRICS = ("completion", "tokens", "hitl", "compaction", "dag", "simplicity", "adversarial")
MODEL_PINNED = "mlx-community--Qwen3.5-4B-MLX-4bit"
RESULT_DIR = Path("benchmarks/results/compare-suite")


def _rival_langgraph_version() -> str:
    try:
        from importlib.metadata import version

        return version("langgraph")
    except Exception as e:
        logger.warning("langgraph version unknown: %s", e)
        return "unavailable"


async def _completion_tokens(metrics: list[str], mlx_url: str, model: str, smoke: bool) -> dict:
    from ..harness_bench.model_client import ModelClient
    from .langgraph_rival import build_agent, run_task
    from .own_runner import run_own_task
    from .rival_chat import MlxChatModel
    from .tasks import SUITE_TASKS, verify_task

    tasks = SUITE_TASKS[:1] if smoke else SUITE_TASKS
    client = ModelClient(base_url=mlx_url, model=model)
    own_rows = []
    for task in tasks:
        ws = RESULT_DIR / "workspaces" / f"own-{task.task_id}"
        row = await run_own_task(client, task, ws)
        row["passed"], row["verify_detail"] = verify_task(task, ws)
        own_rows.append(row)

    rival_rows = []
    for task in tasks:
        ws = RESULT_DIR / "workspaces" / f"lg-{task.task_id}"
        task.materialize(ws)
        model_obj = MlxChatModel(model_name=model, base_url=mlx_url)
        graph = build_agent(model_obj, ws)
        episode = run_task(graph, task.instruction, thread_id=f"bench-{task.task_id}")
        passed, detail = verify_task(task, ws)
        u = episode["usage"]
        rival_rows.append(
            {
                "task_id": task.task_id,
                "side": "langgraph",
                "passed": passed,
                "verify_detail": detail,
                "tokens_in": u.get("input_tokens", 0),
                "tokens_out": u.get("output_tokens", 0),
                "llm_calls": u.get("llm_calls", 0),
                "wall_s": round(u.get("wall_ms", 0) / 1000, 4),
            }
        )
        logger.info(
            "rival arm task=%s passed=%s tokens=%d/%d",
            task.task_id,
            passed,
            u.get("input_tokens", 0),
            u.get("output_tokens", 0),
        )

    report: dict = {"per_task": {"fusion-harness": own_rows, "langgraph": rival_rows}}
    for side, rows in report["per_task"].items():
        completed = [r for r in rows if r["passed"]]
        report[side] = {
            "completion_rate": round(len(completed) / len(rows), 4) if rows else 0.0,
            "tokens_per_completed_task": round(
                sum(r["tokens_in"] + r["tokens_out"] for r in completed) / len(completed), 1
            )
            if completed
            else None,
            "wall_s_total": round(sum(r["wall_s"] for r in rows), 2),
        }
    return report


def _hitl(workdir: Path) -> dict:
    from .hitl import run_hitl_side

    return {
        "fusion-harness": run_hitl_side("harness", workdir / "hitl-harness", repeats=1),
        "langgraph": run_hitl_side("langgraph", workdir / "hitl-langgraph", repeats=1),
    }


def _compaction() -> dict:
    from .compaction import build_transcript, compact_harness, compact_langgraph, probe_state

    msgs = build_transcript()
    return {
        "fusion-harness": probe_state(compact_harness(msgs)),
        "langgraph": probe_state(compact_langgraph(msgs)),
    }


def _dag(workdir: Path) -> dict:
    from .dag_recovery import DIFY_UNAVAILABLE, run_cowork_recovery

    return {"cowork": run_cowork_recovery(workdir / "dag-cowork"), "dify": DIFY_UNAVAILABLE}


def run_comparison(
    metrics: list[str] | None = None,
    smoke: bool = False,
    mlx_url: str = "http://127.0.0.1:11434/v1",
    model: str = MODEL_PINNED,
    out_dir: Path | None = None,
) -> dict:
    selected = list(metrics) if metrics else list(ALL_METRICS)
    unknown = [m for m in selected if m not in ALL_METRICS]
    if unknown:
        raise ValueError(f"unknown metrics: {unknown}; choose from {ALL_METRICS}")
    out = out_dir or RESULT_DIR
    out.mkdir(parents=True, exist_ok=True)
    report: dict = {
        "date": datetime.date.today().isoformat(),
        "issue": 53,
        "model_pinned": model,
        "mlx_url": mlx_url,
        "langgraph_version": _rival_langgraph_version(),
        "smoke": smoke,
        "metrics": {},
    }
    needs_llm = {"completion", "tokens"}
    if needs_llm & set(selected):
        llm_metrics = sorted(needs_llm & set(selected))
        data = asyncio.run(_completion_tokens(llm_metrics, mlx_url, model, smoke))
        for m in llm_metrics:
            report["metrics"][m] = data
    if "hitl" in selected:
        report["metrics"]["hitl"] = _hitl(out)
    if "compaction" in selected:
        report["metrics"]["compaction"] = _compaction()
    if "dag" in selected:
        report["metrics"]["dag"] = _dag(out)
    if "simplicity" in selected:
        from .simplicity import measure

        report["metrics"]["simplicity"] = measure()
    if "adversarial" in selected:
        from .adversarial import run_adversarial

        report["metrics"]["adversarial"] = asyncio.run(run_adversarial(mlx_url, model, smoke, out))

    json_path = out / "report.json"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "report.md").write_text(render_markdown(report), encoding="utf-8")
    # Process-data hygiene: sandbox workspaces are throwaway; keep only the report.
    import shutil

    shutil.rmtree(out / "workspaces", ignore_errors=True)
    logger.info("report written: %s + report.md", json_path)
    return report


def render_markdown(report: dict) -> str:
    from .compaction import FACT_COUNT

    m = report["metrics"]
    lines = [
        f"# Shared-task comparison suite report ({report['date']})",
        "",
        f"- Model: `{report['model_pinned']}` @ {report['mlx_url']} (X-Cache: bypass)",
        f"- langgraph pinned: {report['langgraph_version']} | smoke: {report['smoke']} | issue: #53",
        "",
    ]
    if "completion" in m:
        for side in ("fusion-harness", "langgraph"):
            s = m["completion"][side]
            rate = s["completion_rate"]
            rate_s = f"{rate:.0%}" if rate is not None else "n/a (blocked)"
            wall = s.get("wall_s_total")
            wall_s = f"{wall}s" if wall is not None else "-"
            lines.append(f"- **{side}**: completion rate {rate_s}, wall {wall_s}")
        if m["completion"].get("status"):
            lines.append(f"- completion/tokens status: {m['completion']['status']}")
        lines.append("")
    if "tokens" in m:
        lines.append("| side | tokens / completed task |")
        lines.append("|---|---|")
        for side in ("fusion-harness", "langgraph"):
            v = m["tokens"][side]["tokens_per_completed_task"]
            lines.append(f"| {side} | {v if v is not None else 'n/a (no completions)'} |")
        lines.append("")
    if "hitl" in m:
        lines.append("| side | kill-9 mid-wait -> resumed | resume wall (s) |")
        lines.append("|---|---|---|")
        for side in ("fusion-harness", "langgraph"):
            h = m["hitl"][side]
            lines.append(f"| {side} | {h['resumed_ok']}/{h['repeats']} | {h['resume_wall_s_mean']} |")
        lines.append("")
    if "compaction" in m:
        for side, key in (("fusion-harness", "fusion-harness"), ("langgraph", "langgraph")):
            c = m["compaction"][key]
            lines.append(
                f"- **{side}** compaction recall: pinned_goal={c['pinned_goal']} latest_instruction={c['latest_instruction']} facts_retained={c['facts_retained']}/{FACT_COUNT} score={c['recall_score']}"
            )
        lines.append("")
    if "dag" in m:
        d = m["dag"]
        lines.append(
            f"- DAG recovery (cowork): recovered={d['cowork']['recovered']} after {d['cowork']['injected_failures']} injected failure(s)"
        )
        lines.append(f"- DAG recovery (dify): {d['dify']['error']}")
        lines.append("")
    if "simplicity" in m:
        s = m["simplicity"]
        lines.append("| repo | runtime deps | LOC/node file | cold-start (s) | source |")
        lines.append("|---|---|---|---|---|")
        for repo in ("cowork", "dify"):
            r = s[repo]
            lines.append(
                f"| {repo} | {r['dep_count']} | {r.get('loc_per_node_type') or r.get('loc_per_node_file')} | {r['cold_start_s']} | {r['source']} |"
            )
        lines.append("")
    if "adversarial" in m:
        from .adversarial import render_adversarial

        lines.extend(render_adversarial(m["adversarial"]))
    return "\n".join(lines) + "\n"
