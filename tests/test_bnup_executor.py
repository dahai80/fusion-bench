"""Tests for BNUP 4-dimension executor (#17)."""

from __future__ import annotations

import json

import httpx
import pytest

from fusion_bench.core.plugin_base import ExecutorType, TaskConfig
from fusion_bench.executors.bnup_executor import BNUPEvaluator

VALID_DSL = {
    "meta": {
        "id": "cyl-vol",
        "grade": 6,
        "topic": "圆柱体积",
        "visual_type": "geometry_2d",
        "fallback_type": "tape_diagram",
    },
    "parameters": {
        "base_area": {"label": "底面积", "value": 12.0, "unit": "cm²"},
        "height": {"label": "高", "value": 5.0, "unit": "cm"},
    },
    "entities": [{"id": "cyl", "type": "cylinder", "label": "圆柱", "properties": {}}],
    "pipeline": [
        {
            "step": 1,
            "title": "V",
            "formula": "S*h",
            "eval": "params.base_area * params.height",
            "result_unit": "cm³",
            "visual_state": {"progress_range": [0.0, 0.5], "active_entities": ["cyl"], "action": "highlight"},
        },
        {
            "step": 2,
            "title": "final",
            "formula": "V",
            "eval": "results[1]",
            "result_unit": "cm³",
            "visual_state": {"progress_range": [0.5, 1.0], "active_entities": ["cyl"], "action": "reveal"},
        },
    ],
}


def _valid_output():
    return f"<thinking>分析圆柱体积</thinking>\n<dsl>{json.dumps(VALID_DSL, ensure_ascii=False)}</dsl>"


def _make_executor(monkeypatch, output_text: str, sxs_response: dict | None = None):
    executor = BNUPEvaluator(mlx_base_url="http://localhost:11432/v1")
    lines = [f"data: {json.dumps({'choices': [{'delta': {'content': output_text}}]})}", "data: [DONE]"]

    class FakeStreamCM:
        def __init__(self, url):
            self._url = url

        async def __aenter__(self):
            req = httpx.Request("POST", self._url)
            resp = httpx.Response(200, request=req)

            async def aiter_lines():
                for ln in lines:
                    yield ln

            resp.aiter_lines = aiter_lines
            resp.raise_for_status = lambda: None
            return resp

        async def __aexit__(self, *a):
            return False

    def fake_stream(self, method, url, **kw):
        return FakeStreamCM(url)

    monkeypatch.setattr(httpx.AsyncClient, "stream", fake_stream)

    if sxs_response is not None:

        class StubJudge:
            async def judge_pair(self, a, b, prompt):
                from fusion_bench.judge.sxs_config import SxSVerdict

                return SxSVerdict(
                    winner="a",
                    scores_a={"socratic_guidance": 4, "bnup_misconception_alignment": 4, "dsl_feasibility": 5},
                    scores_b={"socratic_guidance": 3, "bnup_misconception_alignment": 3, "dsl_feasibility": 3},
                    rationale="ok",
                    position_map={"slot1": "a", "slot2": "b"},
                )

        executor._sxs_judge = StubJudge()
    return executor


class TestRegistration:
    def test_executor_type(self):
        assert BNUPEvaluator.executor_type == ExecutorType.BNUP

    def test_name(self):
        assert BNUPEvaluator.name == "bnup"

    def test_is_available(self):
        assert BNUPEvaluator().is_available()


class TestRunValid:
    async def test_valid_output_all_dims(self, monkeypatch):
        executor = _make_executor(monkeypatch, _valid_output(), sxs_response={"winner": "a"})
        config = TaskConfig(
            task_id="bnup-test",
            model="test-model",
            executor_key="bnup",
            params={
                "samples": [
                    {"prompt": "求圆柱体积", "ground_truth": 60.0, "reference_output": "<thinking>ref</thinking>"},
                ],
            },
        )
        result = await executor.run(config)
        assert result.executor_key == "bnup"
        assert result.level == "L4"
        assert len(result.cases) == 1
        case = result.cases[0]
        assert case.meta["format_report"]["all_passed"]
        assert case.meta["math_accuracy"] is True
        assert case.meta["unit_alignment"] is True
        assert case.meta["milestone"] is True
        assert case.meta["socratic_scores"]["socratic_guidance"] == 4
        assert case.meta["ttft_ms"] >= 0
        assert case.meta["tps"] >= 0
        assert "dimensions" in result.meta
        assert result.metric_value > 0


class TestRunMalformed:
    async def test_missing_tags(self, monkeypatch):
        executor = _make_executor(monkeypatch, "no tags at all", sxs_response={"winner": "a"})
        config = TaskConfig(
            task_id="bad",
            model="m",
            executor_key="bnup",
            params={"samples": [{"prompt": "x", "ground_truth": 1.0}]},
        )
        result = await executor.run(config)
        assert len(result.cases) == 1
        case = result.cases[0]
        assert not case.meta["format_report"]["all_passed"]
        assert case.meta["math_accuracy"] is False

    async def test_wrong_ground_truth(self, monkeypatch):
        executor = _make_executor(monkeypatch, _valid_output(), sxs_response={"winner": "a"})
        config = TaskConfig(
            task_id="bad-gt",
            model="m",
            executor_key="bnup",
            params={"samples": [{"prompt": "x", "ground_truth": 999.0, "reference_output": "ref"}]},
        )
        result = await executor.run(config)
        case = result.cases[0]
        assert case.meta["format_report"]["all_passed"]
        assert case.meta["math_accuracy"] is False


class TestRunEdge:
    async def test_no_samples(self):
        executor = BNUPEvaluator()
        config = TaskConfig(task_id="empty", model="m", executor_key="bnup", params={})
        result = await executor.run(config)
        assert not result.cases
        assert result.errors
        assert "no samples" in result.errors[0]

    async def test_no_reference_skips_sxs(self, monkeypatch):
        executor = _make_executor(monkeypatch, _valid_output())
        config = TaskConfig(
            task_id="no-ref",
            model="m",
            executor_key="bnup",
            params={"samples": [{"prompt": "x", "ground_truth": 60.0}]},
        )
        result = await executor.run(config)
        case = result.cases[0]
        assert case.meta["socratic_scores"] == {}


class TestComposite:
    def test_composite_perfect(self):
        executor = BNUPEvaluator()
        dims = {
            "format": 1.0,
            "math_accuracy": 1.0,
            "unit_alignment": 1.0,
            "milestone": 1.0,
            "socratic": 5.0,
            "tps": 25.0,
        }
        score = executor._composite_score(dims)
        assert score == pytest.approx(1.0)

    def test_composite_zero(self):
        executor = BNUPEvaluator()
        dims = {
            "format": 0.0,
            "math_accuracy": 0.0,
            "unit_alignment": 0.0,
            "milestone": 0.0,
            "socratic": 0.0,
            "tps": 0.0,
        }
        score = executor._composite_score(dims)
        assert score == 0.0
