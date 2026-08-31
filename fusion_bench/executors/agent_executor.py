"""L2 Agent evaluation executor — multi-turn sandbox + trajectory scoring.

Imported by executors/__init__.py register_all(). Uses ExecutorPlugin ABC from core/plugin_base.
Data schema: AgentScenario (scenario_id, instruction, expected_behavior, eval_criteria), EvalResult.
API: calls /chat/completions on fusion-mlx. No new public API added.
User instruction: "关闭#10作为无效单，继续修复其他issue，issue全部修复完成" (#11 multi-turn sandbox).
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from fusion_bench.core.plugin_base import (
    CaseResult,
    EvalResult,
    ExecutorPlugin,
    ExecutorType,
    TaskConfig,
)
from fusion_bench.judge import get_judge
from fusion_bench.judge.config import JudgeInput
from fusion_bench.storage.judge_store import JudgeStore

logger = logging.getLogger(__name__)

_TOOL_CALL_RE = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)
_ARITH_TOKEN_RE = re.compile(r"\d+\.?\d*|[+\-*/()]")


def _safe_arith(expr: str) -> float:
    """Shunting-yard arithmetic evaluator — no eval(), supports + - * / ( ) and numbers only."""
    tokens = _ARITH_TOKEN_RE.findall(expr.replace(" ", ""))
    if not tokens:
        raise ValueError("empty expression")
    prec = {"+": 1, "-": 1, "*": 2, "/": 2}
    output: list[float | str] = []
    ops: list[str] = []
    prev = None
    for tok in tokens:
        if tok and tok[0].isdigit():
            output.append(float(tok))
            prev = "num"
        elif tok == "(":
            ops.append(tok)
            prev = "("
        elif tok == ")":
            while ops and ops[-1] != "(":
                output.append(ops.pop())
            if not ops:
                raise ValueError("mismatched parens")
            ops.pop()
            prev = ")"
        elif tok in prec:
            if tok == "-" and (prev is None or prev in {"(", "op"}):
                output.append(0.0)
            while ops and ops[-1] != "(" and prec.get(ops[-1], 0) >= prec[tok]:
                output.append(ops.pop())
            ops.append(tok)
            prev = "op"
        else:
            raise ValueError(f"bad token: {tok}")
    while ops:
        if ops[-1] == "(":
            raise ValueError("mismatched parens")
        output.append(ops.pop())
    stack: list[float] = []
    for item in output:
        if isinstance(item, float):
            stack.append(item)
        else:
            if len(stack) < 2:
                raise ValueError("bad expression")
            b = stack.pop()
            a = stack.pop()
            if item == "+":
                stack.append(a + b)
            elif item == "-":
                stack.append(a - b)
            elif item == "*":
                stack.append(a * b)
            elif item == "/":
                if b == 0:
                    raise ZeroDivisionError("divide by zero")
                stack.append(a / b)
    if len(stack) != 1:
        raise ValueError("bad expression")
    return stack[0]


@dataclass
class AgentScenario:
    scenario_id: str
    instruction: str
    expected_behavior: str
    eval_criteria: list[str] = field(default_factory=list)
    tools_available: list[str] = field(default_factory=list)
    max_turns: int = 3
    expected_tool_calls: list[str] = field(default_factory=list)
    expected_final_answer: str = ""


@dataclass
class TurnRecord:
    turn: int
    role: str
    content: str
    tool_call: dict[str, Any] | None = None
    tool_result: Any = None


class ToolSandbox:
    """Deterministic in-process tool sandbox — no exec()/eval() on user input."""

    def __init__(self, tools_available: list[str]):
        self.tools_available = list(tools_available)

    def execute(self, tool_name: str, args: dict[str, Any]) -> Any:
        if tool_name not in self.tools_available:
            logger.warning("Sandbox: tool '%s' not available", tool_name)
            return {"error": f"tool '{tool_name}' not available"}
        handlers = {
            "search": self._tool_search,
            "weather": self._tool_weather,
            "calculator": self._tool_calculator,
            "calc": self._tool_calculator,
            "file_read": self._tool_file_read,
        }
        fn = handlers.get(tool_name)
        if fn is None:
            logger.info("Sandbox: tool '%s' has no handler, returning ack", tool_name)
            return {"ok": True, "tool": tool_name, "args": args}
        try:
            return fn(args)
        except Exception as e:
            logger.error("Sandbox: tool '%s' raised: %s", tool_name, e)
            return {"error": str(e)}

    @staticmethod
    def _tool_search(args: dict[str, Any]) -> Any:
        query = str(args.get("query", args.get("q", "")))
        return {"results": [f"top result for '{query}'"], "query": query}

    @staticmethod
    def _tool_weather(args: dict[str, Any]) -> Any:
        city = str(args.get("city", args.get("location", "unknown")))
        return {"city": city, "temp_c": 20, "condition": "clear"}

    @staticmethod
    def _tool_calculator(args: dict[str, Any]) -> Any:
        expr = str(args.get("expr", args.get("expression", "")))
        if not re.fullmatch(r"[\d\s+\-*/().]+", expr):
            return {"error": "invalid expression"}
        try:
            result = _safe_arith(expr)
        except (ValueError, ZeroDivisionError) as e:
            return {"error": str(e)}
        return {"result": result}

    @staticmethod
    def _tool_file_read(args: dict[str, Any]) -> Any:
        path = str(args.get("path", ""))
        return {"path": path, "content": f"mock content of {path}"}


class TrajectoryScorer:
    """Scores an agent trajectory: tool correctness + self-correction."""

    @staticmethod
    def score(turns: list[TurnRecord], scenario: AgentScenario) -> dict[str, Any]:
        tool_calls = [t.tool_call for t in turns if t.tool_call]
        tool_correct = 0
        tool_wrong_name = 0
        for tc in tool_calls:
            name = tc.get("name", "") if tc else ""
            if name in scenario.tools_available:
                tool_correct += 1
            else:
                tool_wrong_name += 1
        tool_total = len(tool_calls)
        tool_accuracy = tool_correct / tool_total if tool_total else 0.0

        expected_set = set(scenario.expected_tool_calls)
        called_set = {tc.get("name", "") for tc in tool_calls if tc}
        expected_hit = len(expected_set & called_set)
        expected_coverage = expected_hit / len(expected_set) if expected_set else 1.0

        self_corrections = 0
        for i in range(1, len(turns)):
            prev = turns[i - 1].content.lower()
            cur = turns[i].content.lower()
            if any(k in cur for k in ("sorry", "correction", "actually", "mistake")) and prev:
                self_corrections += 1

        final_text = turns[-1].content if turns else ""
        answer_correct = bool(scenario.expected_final_answer and scenario.expected_final_answer in final_text)

        traj_score = (
            0.4 * tool_accuracy
            + 0.3 * expected_coverage
            + 0.2 * (1.0 if self_corrections >= 1 and tool_total > 0 else 0.0)
            + 0.1 * (1.0 if answer_correct else 0.0)
        )
        return {
            "tool_total": tool_total,
            "tool_correct": tool_correct,
            "tool_wrong_name": tool_wrong_name,
            "tool_accuracy": round(tool_accuracy, 4),
            "expected_coverage": round(expected_coverage, 4),
            "self_corrections": self_corrections,
            "answer_correct": answer_correct,
            "trajectory_score": round(traj_score, 4),
        }


class AgentExecutor(ExecutorPlugin):
    """L2 Agent layer executor — multi-turn sandbox + trajectory scoring."""

    name = "agent"
    executor_type = ExecutorType.AGENT

    def __init__(self, base_url: str = "http://localhost:11432/v1"):
        self.base_url = base_url.rstrip("/")

    def is_available(self) -> bool:
        return True

    async def run(self, task_config: TaskConfig) -> EvalResult:
        logger.info("AgentExecutor: running agent eval for model=%s", task_config.model)
        scenarios = self._load_scenarios(task_config)
        if not scenarios:
            return EvalResult(
                task_id=task_config.task_id,
                executor_key=self.name,
                model=task_config.model,
                level="L2",
                metric_name="agent_score",
                metric_value=0.0,
                errors=["No agent scenarios found"],
            )

        case_results: list[CaseResult] = []
        traj_scores: list[float] = []
        for scenario in scenarios:
            result = await self._evaluate_scenario(scenario, task_config)
            case_results.append(result)
            ts = result.meta.get("trajectory", {}).get("trajectory_score", 0.0)
            traj_scores.append(ts)

        passed = sum(1 for c in case_results if c.passed)
        score = passed / len(case_results) if case_results else 0.0
        avg_traj = sum(traj_scores) / len(traj_scores) if traj_scores else 0.0
        return EvalResult(
            task_id=task_config.task_id,
            executor_key=self.name,
            model=task_config.model,
            level="L2",
            metric_name="agent_score",
            metric_value=round(score, 4),
            cases=case_results,
            meta={
                "scenarios_total": len(scenarios),
                "scenarios_passed": passed,
                "avg_trajectory_score": round(avg_traj, 4),
            },
        )

    def _load_scenarios(self, task_config: TaskConfig) -> list[AgentScenario]:
        raw = task_config.params.get("scenarios", [])
        if raw:
            return [AgentScenario(**s) if isinstance(s, dict) else s for s in raw]
        return self._default_scenarios()

    @staticmethod
    def _default_scenarios() -> list[AgentScenario]:
        return [
            AgentScenario(
                scenario_id="agent-follow-instruction",
                instruction="List exactly 3 colors in a bullet list.",
                expected_behavior="Returns a list with exactly 3 colors",
                eval_criteria=["contains_3_items", "bullet_format"],
                max_turns=1,
            ),
            AgentScenario(
                scenario_id="agent-tool-selection",
                instruction="Search for the weather in Tokyo and summarize it.",
                expected_behavior="Calls search/weather tool, then summarizes",
                eval_criteria=["mentions_tool", "relevant_query"],
                tools_available=["search", "weather"],
                expected_tool_calls=["search", "weather"],
                max_turns=3,
            ),
            AgentScenario(
                scenario_id="agent-multi-step",
                instruction="First calculate 15 * 7, then subtract 10 from the result.",
                expected_behavior="Shows step-by-step calculation: 105 - 10 = 95",
                eval_criteria=["shows_steps", "correct_final_answer"],
                tools_available=["calculator"],
                expected_tool_calls=["calculator"],
                expected_final_answer="95",
                max_turns=3,
            ),
            AgentScenario(
                scenario_id="agent-self-correction",
                instruction="Calculate 9 * 8. If you make a mistake, correct yourself.",
                expected_behavior="Self-corrects to 72",
                eval_criteria=["shows_steps", "correct_final_answer"],
                tools_available=["calculator"],
                expected_tool_calls=["calculator"],
                expected_final_answer="72",
                max_turns=4,
            ),
            AgentScenario(
                scenario_id="agent-file-read",
                instruction="Read the file /tmp/config.json and report its content.",
                expected_behavior="Calls file_read tool, reports content",
                eval_criteria=["mentions_tool", "reports_content"],
                tools_available=["file_read"],
                expected_tool_calls=["file_read"],
                max_turns=2,
            ),
        ]

    async def _evaluate_scenario(
        self,
        scenario: AgentScenario,
        task_config: TaskConfig,
    ) -> CaseResult:
        t0 = time.time()
        try:
            turns = await self._run_multi_turn(scenario, task_config)
            latency = (time.time() - t0) * 1000
            final_response = turns[-1].content if turns else ""
            criteria_eval = self._eval_response(scenario, final_response)
            traj = TrajectoryScorer.score(turns, scenario)
            rule_score = 0.5 * criteria_eval["score"] + 0.5 * traj["trajectory_score"]
            final_score, judge_source, judge_meta = await self._apply_judge(
                scenario, final_response, rule_score, task_config
            )
            passed = final_score >= 0.5
            meta = {
                "scenario_id": scenario.scenario_id,
                "turns": len(turns),
                "trajectory": traj,
                **criteria_eval["details"],
            }
            if judge_source:
                meta["judge_source"] = judge_source
                meta.update(judge_meta)
            return CaseResult(
                input_text=scenario.instruction,
                expected=scenario.expected_behavior,
                actual=final_response[:500],
                score=final_score,
                passed=passed,
                latency_ms=latency,
                meta=meta,
            )
        except Exception as e:
            logger.error("Agent scenario %s failed: %s", scenario.scenario_id, e)
            return CaseResult(
                input_text=scenario.instruction,
                expected=scenario.expected_behavior,
                actual=str(e),
                score=0.0,
                passed=False,
                latency_ms=(time.time() - t0) * 1000,
                meta={"scenario_id": scenario.scenario_id, "error": str(e)},
            )

    async def _run_multi_turn(
        self,
        scenario: AgentScenario,
        task_config: TaskConfig,
    ) -> list[TurnRecord]:
        sandbox = ToolSandbox(scenario.tools_available)
        messages: list[dict[str, str]] = [
            {"role": "system", "content": self._system_prompt(scenario)},
            {"role": "user", "content": scenario.instruction},
        ]
        turns: list[TurnRecord] = []
        max_turns = max(1, scenario.max_turns)
        for turn_idx in range(max_turns):
            response = await self._call_model(messages, task_config)
            turns.append(TurnRecord(turn=turn_idx, role="assistant", content=response))
            tool_call = self._parse_tool_call(response)
            if tool_call:
                turns[-1].tool_call = tool_call
                tool_result = sandbox.execute(tool_call.get("name", ""), tool_call.get("args", {}))
                turns[-1].tool_result = tool_result
                messages.append({"role": "assistant", "content": response})
                messages.append(
                    {
                        "role": "user",
                        "content": f"Tool result: {tool_result}. Continue or give final answer.",
                    }
                )
            else:
                messages.append({"role": "assistant", "content": response})
                if turn_idx == 0 and not scenario.tools_available:
                    break
                if turn_idx >= 1:
                    break
        return turns

    @staticmethod
    def _system_prompt(scenario: AgentScenario) -> str:
        prompt = "You are a helpful AI assistant."
        if scenario.tools_available:
            tools_desc = ", ".join(scenario.tools_available)
            prompt += (
                f" Available tools: {tools_desc}. "
                'To call a tool, emit a json fence: ```json\n{"name": "<tool>", "args": {...}}\n```'
            )
        return prompt

    async def _call_model(
        self,
        messages: list[dict[str, str]],
        task_config: TaskConfig,
    ) -> str:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                json={
                    "model": task_config.model,
                    "messages": messages,
                    "max_tokens": task_config.params.get("max_tokens", 1024),
                    "temperature": task_config.params.get("temperature", 0.3),
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("choices", [{}])[0].get("message", {}).get("content", "")

    @staticmethod
    def _parse_tool_call(response: str) -> dict[str, Any] | None:
        m = _TOOL_CALL_RE.search(response)
        if not m:
            return None
        try:
            payload = json.loads(m.group(1))
            if "name" in payload:
                if "args" not in payload:
                    payload["args"] = payload.get("arguments", {})
                return payload
        except (json.JSONDecodeError, AttributeError) as e:
            logger.debug("Tool call parse failed: %s", e)
        return None

    @staticmethod
    def _eval_response(scenario: AgentScenario, response: str) -> dict:
        criteria_checks: dict[str, bool] = {}
        resp_lower = response.lower()
        for criterion in scenario.eval_criteria:
            if criterion == "contains_3_items":
                lines = [
                    ln.strip() for ln in response.split("\n") if ln.strip().startswith(("- ", "* ", "1.", "2.", "3."))
                ]
                criteria_checks[criterion] = len(lines) >= 3
            elif criterion == "bullet_format":
                criteria_checks[criterion] = any(ln.strip().startswith(("- ", "* ")) for ln in response.split("\n"))
            elif criterion == "mentions_tool":
                tool_words = scenario.tools_available + ["tool", "use", "search", "call"]
                criteria_checks[criterion] = any(w in resp_lower for w in tool_words)
            elif criterion == "relevant_query":
                criteria_checks[criterion] = any(w in resp_lower for w in ["tokyo", "weather", "japan"])
            elif criterion == "shows_steps":
                step_markers = ["first", "then", "step", "1.", "2.", "="]
                criteria_checks[criterion] = sum(1 for m in step_markers if m in resp_lower) >= 2
            elif criterion == "correct_final_answer":
                if scenario.expected_final_answer:
                    criteria_checks[criterion] = scenario.expected_final_answer in response
                else:
                    criteria_checks[criterion] = "95" in response
            elif criterion == "reports_content":
                criteria_checks[criterion] = any(w in resp_lower for w in ["content", "mock", "config"])
            else:
                criteria_checks[criterion] = len(response) > 10

        passed_count = sum(1 for v in criteria_checks.values() if v)
        total = len(criteria_checks)
        score = passed_count / total if total > 0 else 0.0
        passed = score >= 0.5
        return {"score": score, "passed": passed, "details": criteria_checks}

    async def _apply_judge(
        self,
        scenario: AgentScenario,
        final_response: str,
        rule_score: float,
        task_config: TaskConfig,
    ) -> tuple[float, str | None, dict]:
        # Returns (final_score, judge_source, judge_meta). judge_source None = no judge.
        judge_name = task_config.params.get("judge")
        if not judge_name:
            return rule_score, None, {}
        store = JudgeStore()
        judge_config = store.get(judge_name)
        store.close()
        if judge_config is None:
            logger.warning("JudgeConfig '%s' not found; rule-only scoring", judge_name)
            return rule_score, None, {}
        if judge_config.judge_type == "rule":
            return rule_score, "rule", {}
        try:
            judge = get_judge(judge_config)
            verdict = await judge.judge(
                JudgeInput(
                    prompt=scenario.instruction,
                    expected=scenario.expected_final_answer or scenario.expected_behavior,
                    actual=final_response,
                    criteria=judge_config.criteria,
                    rubric=judge_config.rubric,
                )
            )
        except Exception as e:
            logger.warning("judge_fallback for scenario %s: %s", scenario.scenario_id, e)
            return rule_score, "fallback", {"judge_fallback": str(e)}
        weight = judge_config.weight
        if judge_config.judge_type == "llm":
            final = verdict.score
        else:  # hybrid
            final = weight * verdict.score + (1 - weight) * rule_score
        return final, judge_config.judge_type, {"judge_score": verdict.score, "judge_reasoning": verdict.reasoning}
