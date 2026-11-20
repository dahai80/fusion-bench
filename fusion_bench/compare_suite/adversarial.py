"""Metric 7 — adversarial injection resistance (issue #54).

Runs the versioned YAML attack corpus through both arms on the identical
pinned model, then grades end state only (no model calls): utility (benign
task still completed) and attack success (injected action performed).
"""

from __future__ import annotations

import logging
from pathlib import Path

from .attacks import grade_case, load_cases
from .langgraph_rival import build_agent, run_task
from .own_runner import run_own_task
from .rival_chat import MlxChatModel

logger = logging.getLogger(__name__)


async def run_adversarial(mlx_url: str, model: str, smoke: bool, out: Path) -> dict:
    from ..harness_bench.model_client import ModelClient

    cases = load_cases()
    if smoke:
        cases = cases[:1]
    per_case: dict = {"fusion-harness": [], "langgraph": []}

    client = ModelClient(base_url=mlx_url, model=model)
    for case in cases:
        ws = out / "workspaces" / f"adv-own-{case.case_id}"
        case.task.materialize(ws)
        await run_own_task(client, case.task, ws)
        g = grade_case(case, ws)
        g["case_id"] = case.case_id
        g["vector"] = case.vector
        per_case["fusion-harness"].append(g)

    for case in cases:
        ws = out / "workspaces" / f"adv-lg-{case.case_id}"
        case.task.materialize(ws)
        model_obj = MlxChatModel(model_name=model, base_url=mlx_url)
        graph = build_agent(model_obj, ws)
        run_task(graph, case.task.instruction, thread_id=f"adv-{case.case_id}")
        g = grade_case(case, ws)
        g["case_id"] = case.case_id
        g["vector"] = case.vector
        per_case["langgraph"].append(g)

    report: dict = {"cases": len(cases), "per_case": per_case}
    for side, rows in per_case.items():
        report[side] = {
            "attack_success_rate": round(sum(1 for r in rows if r["attack_success"]) / len(rows), 4) if rows else None,
            "utility_rate": round(sum(1 for r in rows if r["utility"]) / len(rows), 4) if rows else None,
        }
        logger.info(
            "adversarial side=%s asr=%s utility=%s",
            side,
            report[side]["attack_success_rate"],
            report[side]["utility_rate"],
        )
    return report


def render_adversarial(adv: dict) -> list[str]:
    lines = [
        "| case | vector | harness util | harness ASR | langgraph util | langgraph ASR |",
        "|---|---|---|---|---|---|",
    ]
    own = {r["case_id"]: r for r in adv["per_case"]["fusion-harness"]}
    lg = {r["case_id"]: r for r in adv["per_case"]["langgraph"]}
    for case_id in own:
        o_row, lg_row = own[case_id], lg.get(case_id, {})
        lines.append(
            f"| {case_id} | {o_row['vector']} | {o_row['utility']} | {o_row['attack_success']} | {lg_row.get('utility')} | {lg_row.get('attack_success')} |"
        )
    lines.append("")
    for side in ("fusion-harness", "langgraph"):
        s = adv[side]
        lines.append(
            f"- **{side}**: attack success rate {s['attack_success_rate']}, utility rate {s['utility_rate']} ({adv['cases']} cases)"
        )
    lines.append("")
    return lines
