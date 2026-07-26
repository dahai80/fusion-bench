"""L2 Agent evaluation executor - tests agent behavior via fusion-mlx HTTP API.

Imported by executors/__init__.py register_all(). Uses ExecutorPlugin ABC from core/plugin_base.
Data schema: AgentScenario (scenario_id, instruction, expected_behavior, eval_criteria), EvalResult.
API: calls /chat/completions on fusion-mlx. No new public API added.
User instruction: "把所有没完全做完，没启动做，有差距的全部启动补齐" (P1-1 L2 Agent executor).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import httpx

from fusion_bench.core.plugin_base import (
    CaseResult,
    EvalResult,
    ExecutorPlugin,
    ExecutorType,
    TaskConfig,
)

logger = logging.getLogger(__name__)


@dataclass
class AgentScenario:
    scenario_id: str
    instruction: str
    expected_behavior: str
    eval_criteria: list[str] = field(default_factory=list)
    tools_available: list[str] = field(default_factory=list)
    max_turns: int = 3


class AgentExecutor(ExecutorPlugin):
    """L2 Agent layer executor - evaluates agent behavior scenarios."""

    name = "agent"
    executor_type = ExecutorType.AGENT

    def __init__(self, base_url: str = "http://localhost:11434/v1"):
        self.base_url = base_url.rstrip("/")

    def is_available(self) -> bool:
        try:
            resp = httpx.get(f"{self.base_url}/models", timeout=5.0)
            return resp.status_code == 200
        except Exception:
            return False

    async def run(self, task_config: TaskConfig) -> EvalResult:
        logger.info("AgentExecutor: running agent eval for model=%s", task_config.model)
        scenarios = self._load_scenarios(task_config)
        if not scenarios:
            return EvalResult(
                score=0.0,
                metrics={"scenarios_total": 0},
                details={"error": "No agent scenarios found"},
            )

        case_results: list[CaseResult] = []
        for scenario in scenarios:
            result = await self._evaluate_scenario(scenario, task_config)
            case_results.append(result)

        passed = sum(1 for c in case_results if c.passed)
        score = passed / len(case_results) if case_results else 0.0
        return EvalResult(
            score=score,
            metrics={"scenarios_total": len(scenarios), "scenarios_passed": passed},
            case_results=case_results,
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
                expected_behavior="Attempts to use a search/weather tool",
                eval_criteria=["mentions_tool", "relevant_query"],
                tools_available=["search", "weather"],
                max_turns=2,
            ),
            AgentScenario(
                scenario_id="agent-multi-step",
                instruction="First calculate 15 * 7, then subtract 10 from the result.",
                expected_behavior="Shows step-by-step calculation: 105 - 10 = 95",
                eval_criteria=["shows_steps", "correct_final_answer"],
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
            response = await self._call_model(scenario, task_config)
            latency = (time.time() - t0) * 1000
            eval_result = self._eval_response(scenario, response)
            return CaseResult(
                input_text=scenario.instruction,
                expected=scenario.expected_behavior,
                actual=response[:500],
                score=eval_result["score"],
                passed=eval_result["passed"],
                latency_ms=latency,
                meta={"scenario_id": scenario.scenario_id, **eval_result["details"]},
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

    async def _call_model(self, scenario: AgentScenario, task_config: TaskConfig) -> str:
        messages = [{"role": "system", "content": "You are a helpful AI assistant."}]
        if scenario.tools_available:
            tools_desc = ", ".join(scenario.tools_available)
            messages[0]["content"] += f" Available tools: {tools_desc}."
        messages.append({"role": "user", "content": scenario.instruction})

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
                tool_words = scenario.tools_available + [
                    "tool",
                    "use",
                    "search",
                    "call",
                ]
                criteria_checks[criterion] = any(w in resp_lower for w in tool_words)
            elif criterion == "relevant_query":
                criteria_checks[criterion] = any(w in resp_lower for w in ["tokyo", "weather", "japan"])
            elif criterion == "shows_steps":
                step_markers = ["first", "then", "step", "1.", "2.", "="]
                criteria_checks[criterion] = sum(1 for m in step_markers if m in resp_lower) >= 2
            elif criterion == "correct_final_answer":
                criteria_checks[criterion] = "95" in response
            else:
                criteria_checks[criterion] = len(response) > 10

        passed_count = sum(1 for v in criteria_checks.values() if v)
        total = len(criteria_checks)
        score = passed_count / total if total > 0 else 0.0
        passed = score >= 0.5
        return {"score": score, "passed": passed, "details": criteria_checks}
