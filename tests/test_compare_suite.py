"""Issue #53 — shared-task comparison suite: offline tests.

LLM-backed arms are exercised with mocked transport; framework arms skip
when the optional rival/kernel deps are absent (CI installs the `rival`
extra for the langgraph arm).
"""

from __future__ import annotations

import json

import pytest

from fusion_bench.compare_suite.tasks import SUITE_TASKS, verify_task


class TestSharedTasks:
    def test_taskset_is_fixed_and_verified(self, tmp_path):
        assert [t.task_id for t in SUITE_TASKS] == ["typo-fix", "config-write", "count-words"]
        for task in SUITE_TASKS:
            ws = tmp_path / task.task_id
            task.materialize(ws)
            passed, detail = verify_task(task, ws)
            assert not passed, "fresh workspace must not pass before the agent acts"
            assert detail

    def test_verifier_accepts_solution(self, tmp_path):
        from fusion_bench.compare_suite.tasks import WORD_COUNT

        ws = tmp_path
        (ws / "greeting_fixed.txt").write_text("Hello world, welcome to the demo app.\n", encoding="utf-8")
        (ws / "config.json").write_text(json.dumps({"mode": "fast", "retries": 3}), encoding="utf-8")
        (ws / "words.txt").write_text("a b c\n", encoding="utf-8")
        (ws / "count.txt").write_text(str(WORD_COUNT), encoding="utf-8")
        for task in SUITE_TASKS:
            passed, detail = verify_task(task, ws)
            assert passed, f"{task.task_id}: {detail}"


class TestRivalChat:
    def test_bind_tools_returns_copy_with_specs(self):
        pytest.importorskip("langgraph")
        from fusion_bench.compare_suite.rival_chat import MlxChatModel

        model = MlxChatModel(api_key="k")
        bound = model.bind_tools(
            [
                {
                    "type": "function",
                    "function": {"name": "t", "description": "d", "parameters": {"type": "object", "properties": {}}},
                }
            ]
        )
        assert bound is not model
        assert bound.tools_spec[0]["function"]["name"] == "t"
        assert model.tools_spec == []

    def test_generate_accumulates_usage_and_tool_calls(self, monkeypatch):
        from fusion_bench.compare_suite.rival_chat import MlxChatModel

        payload_holder = {}

        def fake_post(url, json=None, headers=None, timeout=None):
            payload_holder["url"] = url
            payload_holder["body"] = json
            payload_holder["headers"] = headers

            class R:
                def raise_for_status(self):
                    pass

                def json(self):
                    return {
                        "choices": [
                            {
                                "message": {
                                    "content": None,
                                    "tool_calls": [
                                        {
                                            "id": "c1",
                                            "type": "function",
                                            "function": {"name": "run_bash", "arguments": '{"cmd": "ls"}'},
                                        }
                                    ],
                                }
                            }
                        ],
                        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                    }

            return R()

        import fusion_bench.compare_suite.rival_chat as rc

        monkeypatch.setattr(rc.httpx, "post", fake_post)
        model = MlxChatModel(api_key="k", tools_spec=[{"type": "function", "function": {"name": "run_bash"}}])
        from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

        result = model._generate(
            [SystemMessage(content="s"), HumanMessage(content="hi"), ToolMessage(content="out", tool_call_id="c1")]
        )
        ai = result.generations[0].message
        assert ai.tool_calls[0]["name"] == "run_bash"
        assert ai.tool_calls[0]["args"] == {"cmd": "ls"}
        assert model.usage["input_tokens"] == 10 and model.usage["output_tokens"] == 5
        assert model.usage["llm_calls"] == 1
        assert payload_holder["headers"]["X-Cache"] == "bypass"
        assert payload_holder["body"]["messages"][2]["role"] == "tool"

    def test_bad_tool_arguments_dropped(self, monkeypatch):
        from fusion_bench.compare_suite.rival_chat import MlxChatModel

        def fake_post(url, json=None, headers=None, timeout=None):
            class R:
                def raise_for_status(self):
                    pass

                def json(self):
                    return {
                        "choices": [
                            {
                                "message": {
                                    "content": "x",
                                    "tool_calls": [
                                        {
                                            "id": "c1",
                                            "type": "function",
                                            "function": {"name": "run_bash", "arguments": "not-json"},
                                        }
                                    ],
                                }
                            }
                        ],
                        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                    }

            return R()

        import fusion_bench.compare_suite.rival_chat as rc

        monkeypatch.setattr(rc.httpx, "post", fake_post)
        model = MlxChatModel(api_key="k")
        from langchain_core.messages import HumanMessage

        ai = model._generate([HumanMessage(content="hi")]).generations[0].message
        assert ai.tool_calls == []


class TestCompaction:
    def test_transcript_deterministic(self):
        from fusion_bench.compare_suite.compaction import build_transcript

        assert build_transcript() == build_transcript()

    def test_probe_scoring(self):
        from fusion_bench.compare_suite.compaction import LATEST_INSTRUCTION, PINNED_GOAL, probe_state

        full = [
            {"role": "user", "content": f"Task goal: {PINNED_GOAL}"},
            {"role": "user", "content": LATEST_INSTRUCTION},
        ]
        probes = probe_state(full)
        assert probes["recall_score"] == 1.0
        assert probe_state([{"role": "user", "content": "nothing"}])["recall_score"] == 0.0

    def test_harness_compaction_retains_pinned_goal(self):
        pytest.importorskip("fusion_harness")
        from fusion_bench.compare_suite.compaction import build_transcript, compact_harness, probe_state

        probes = probe_state(compact_harness(build_transcript()))
        assert probes["pinned_goal"] is True
        assert probes["latest_instruction"] is True

    def test_langgraph_summary_node_keeps_recent(self):
        pytest.importorskip("langgraph")
        from fusion_bench.compare_suite.compaction import build_transcript, compact_langgraph, probe_state

        probes = probe_state(compact_langgraph(build_transcript()))
        assert probes["latest_instruction"] is True


class TestHitl:
    def test_harness_gate_survives_sigkill(self, tmp_path):
        pytest.importorskip("fusion_harness")
        from fusion_bench.compare_suite.hitl import run_hitl_side

        stats = run_hitl_side("harness", tmp_path / "h", repeats=1)
        assert stats["resume_rate"] == 1.0
        assert stats["resume_wall_s_mean"] is not None

    def test_langgraph_gate_survives_sigkill(self, tmp_path):
        pytest.importorskip("langgraph")
        pytest.importorskip("langgraph.checkpoint.sqlite")
        from fusion_bench.compare_suite.hitl import run_hitl_side

        stats = run_hitl_side("langgraph", tmp_path / "l", repeats=1)
        assert stats["resume_rate"] == 1.0


class TestDagRecovery:
    def test_cowork_recovers_from_transient_failures(self, tmp_path):
        pytest.importorskip("fusion_cowork")
        from fusion_bench.compare_suite.dag_recovery import run_cowork_recovery

        result = run_cowork_recovery(tmp_path)
        assert result["recovered"] is True
        assert result["steps"]["flaky"]["attempt"] == result["injected_failures"] + 1
        assert "SUCCESS" in result["steps"]["c"]["status"]

    def test_dify_cell_reports_unavailable(self):
        from fusion_bench.compare_suite.dag_recovery import DIFY_UNAVAILABLE

        assert DIFY_UNAVAILABLE["recovered"] is None
        assert DIFY_UNAVAILABLE["error"].startswith("unavailable")


class TestSimplicity:
    def test_frozen_dify_cell(self):
        from fusion_bench.compare_suite.simplicity import DIFY_FROZEN

        assert DIFY_FROZEN["source"].startswith("offline-frozen")
        assert DIFY_FROZEN["dep_count"] is None

    def test_measure_live_when_cowork_present(self):
        from fusion_bench.compare_suite import simplicity

        if not simplicity.COWORK_ROOT.exists():
            pytest.skip("fusion-cowork checkout not present")
        data = simplicity.measure()
        assert data["cowork"]["dep_count"] >= 0
        assert data["cowork"]["source"] == "measured live"


class TestCompareOrchestrator:
    def test_unknown_metric_rejected(self, tmp_path):
        from fusion_bench.compare_suite.compare import run_comparison

        with pytest.raises(ValueError):
            run_comparison(metrics=["nope"], out_dir=tmp_path)

    def test_render_markdown_sections(self, tmp_path):
        from fusion_bench.compare_suite.compare import render_markdown

        report = {
            "date": "2026-11-20",
            "model_pinned": "m",
            "mlx_url": "http://x",
            "langgraph_version": "1.2.10",
            "smoke": True,
            "metrics": {
                "completion": {
                    "fusion-harness": {"completion_rate": 1.0, "wall_s_total": 1.0},
                    "langgraph": {"completion_rate": 0.5, "wall_s_total": 2.0},
                },
                "tokens": {
                    "fusion-harness": {"tokens_per_completed_task": 100.0},
                    "langgraph": {"tokens_per_completed_task": None},
                },
                "hitl": {
                    "fusion-harness": {
                        "side": "harness",
                        "repeats": 1,
                        "resumed_ok": 1,
                        "resume_rate": 1.0,
                        "resume_wall_s_mean": 2.3,
                        "failures": [],
                    },
                    "langgraph": {
                        "side": "langgraph",
                        "repeats": 1,
                        "resumed_ok": 1,
                        "resume_rate": 1.0,
                        "resume_wall_s_mean": 0.6,
                        "failures": [],
                    },
                },
                "compaction": {
                    "fusion-harness": {
                        "pinned_goal": True,
                        "latest_instruction": True,
                        "facts_retained": 8,
                        "recall_score": 1.0,
                    },
                    "langgraph": {
                        "pinned_goal": False,
                        "latest_instruction": True,
                        "facts_retained": 8,
                        "recall_score": 0.5,
                    },
                },
                "dag": {"cowork": {"recovered": True, "injected_failures": 2}, "dify": {"error": "unavailable: x"}},
                "simplicity": {
                    "cowork": {
                        "dep_count": 15,
                        "loc_per_node_file": 100.0,
                        "cold_start_s": 0.4,
                        "source": "measured live",
                    },
                    "dify": {
                        "dep_count": None,
                        "loc_per_node_type": None,
                        "cold_start_s": None,
                        "source": "offline-frozen",
                    },
                },
            },
        }
        md = render_markdown(report)
        assert "completion rate 100%" in md
        assert "tokens / completed task" in md
        assert "kill-9 mid-wait" in md
        assert "recall" in md
        assert "unavailable: x" in md
        assert "offline-frozen" in md


class TestAttackCorpus:
    def test_loads_ten_valid_cases(self):
        from fusion_bench.compare_suite.attacks import load_cases

        cases = load_cases()
        assert len(cases) >= 10
        for case in cases:
            assert case.case_id.startswith("attack-")
            assert case.vector
            assert case.injected_file in case.task.setup_files
            assert case.injection

    def test_injection_composed_into_setup_file(self, tmp_path):
        from fusion_bench.compare_suite.attacks import load_cases

        case = load_cases()[0]
        ws = tmp_path / case.case_id
        case.task.materialize(ws)
        assert case.injection in (ws / case.injected_file).read_text(encoding="utf-8")

    def test_fresh_workspace_neither_utility_nor_attack(self, tmp_path):
        from fusion_bench.compare_suite.attacks import grade_case, load_cases

        for case in load_cases():
            ws = tmp_path / case.case_id
            case.task.materialize(ws)
            g = grade_case(case, ws)
            assert not g["utility"], case.case_id
            assert not g["attack_success"], case.case_id

    def test_loader_rejects_bad_specs(self, tmp_path):
        from fusion_bench.compare_suite.attacks import load_cases

        bad = tmp_path / "bad.yaml"
        bad.write_text(
            "id: bad-case\nbenign:\n  instruction: x\n  files:\n    a.txt: hi\n"
            "benign_check:\n  type: file_exists\n  path: a.txt\n"
            "asr:\n  type: nope\n  path: b.txt\nattack:\n  injected_in: a.txt\n  injection: y\n",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="asr.type"):
            load_cases(tmp_path)

    def test_loader_rejects_same_path_specs(self, tmp_path):
        from fusion_bench.compare_suite.attacks import load_cases

        bad = tmp_path / "bad.yaml"
        bad.write_text(
            "id: bad-case\nbenign:\n  instruction: x\n  files:\n    a.txt: hi\n"
            "benign_check:\n  type: file_exists\n  path: b.txt\n"
            "asr:\n  type: file_exists\n  path: b.txt\nattack:\n  injected_in: a.txt\n  injection: y\n",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="different paths"):
            load_cases(tmp_path)

    def test_all_metric_includes_adversarial(self):
        from fusion_bench.compare_suite.compare import ALL_METRICS

        assert "adversarial" in ALL_METRICS


class TestAdversarialGrading:
    def test_eval_spec_types(self, tmp_path):
        from fusion_bench.compare_suite.attacks import eval_spec

        (tmp_path / "keep.txt").write_text("hello world\n", encoding="utf-8")
        assert eval_spec({"type": "file_exists", "path": "keep.txt"}, tmp_path)[0] is True
        assert eval_spec({"type": "file_absent", "path": "gone.txt"}, tmp_path)[0] is True
        assert eval_spec({"type": "file_contains", "path": "keep.txt", "text": "world"}, tmp_path)[0] is True
        assert eval_spec({"type": "file_contains", "path": "keep.txt", "text": "nope"}, tmp_path)[0] is False
        assert eval_spec({"type": "file_exists", "path": "gone.txt"}, tmp_path)[0] is False

    def test_grade_after_simulated_attack(self, tmp_path):
        from fusion_bench.compare_suite.attacks import grade_case, load_cases

        case = load_cases()[0]
        ws = tmp_path
        case.task.materialize(ws)
        (ws / "pwned.txt").write_text("owned\n", encoding="utf-8")
        g = grade_case(case, ws)
        assert g["attack_success"] is True
        assert g["utility"] is False

    def test_grade_after_clean_completion(self, tmp_path):
        from fusion_bench.compare_suite.attacks import grade_case, load_cases

        case = load_cases()[0]
        ws = tmp_path
        case.task.materialize(ws)
        (ws / "summary.txt").write_text("Ship the release notes by Friday.\n", encoding="utf-8")
        g = grade_case(case, ws)
        assert g["utility"] is True
        assert g["attack_success"] is False

    def test_render_adversarial_table(self):
        from fusion_bench.compare_suite.adversarial import render_adversarial

        adv = {
            "cases": 1,
            "per_case": {
                "fusion-harness": [
                    {
                        "case_id": "attack-001-notes-summary",
                        "vector": "direct-instruction",
                        "utility": True,
                        "attack_success": False,
                    }
                ],
                "langgraph": [
                    {
                        "case_id": "attack-001-notes-summary",
                        "vector": "direct-instruction",
                        "utility": True,
                        "attack_success": True,
                    }
                ],
            },
            "fusion-harness": {"attack_success_rate": 0.0, "utility_rate": 1.0},
            "langgraph": {"attack_success_rate": 1.0, "utility_rate": 1.0},
        }
        md = "\n".join(render_adversarial(adv))
        assert "attack-001-notes-summary" in md
        assert "attack success rate 0.0" in md
        assert "attack success rate 1.0" in md
