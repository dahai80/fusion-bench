"""L3 Code evaluation executor - tests code generation via fusion-mlx HTTP API.

Importers/callers: executors/__init__.py register_all() imports and registers CodeExecutor.
Affected API: calls POST /chat/completions on fusion-mlx; no new public API surface.
Data schemas: CodeTestCase dataclass (test_id, prompt, language, expected_patterns, forbidden_patterns); EvalResult from plugin_base.
Constraint: never uses exec()/eval() - only regex pattern matching on generated code.
User instruction: "把所有没完全做完，没启动做，有差距的全部启动补齐" (P2-10).
"""

from __future__ import annotations

import logging
import re
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
class CodeTestCase:
    test_id: str
    prompt: str
    language: str = "python"
    expected_patterns: list[str] = field(default_factory=list)
    forbidden_patterns: list[str] = field(default_factory=list)
    complexity_limit: int = 0


class CodeExecutor(ExecutorPlugin):
    """L3 Code evaluation executor - tests code generation quality."""

    name = "code"
    executor_type = ExecutorType.CODE

    def __init__(self, base_url: str = "http://localhost:11432/v1"):
        self.base_url = base_url.rstrip("/")

    def is_available(self) -> bool:
        return True

    async def run(self, task_config: TaskConfig) -> EvalResult:
        logger.info("CodeExecutor: running code eval for model=%s", task_config.model)
        test_cases = self._load_test_cases(task_config)
        if not test_cases:
            logger.warning("CodeExecutor: no test cases for model=%s", task_config.model)
            return EvalResult(
                task_id=task_config.task_id,
                executor_key=self.name,
                model=task_config.model,
                level="L3",
                metric_name="code_pass_rate",
                metric_value=0.0,
                errors=["No code test cases found"],
            )

        case_results: list[CaseResult] = []
        for tc in test_cases:
            result = await self._evaluate_code(tc, task_config)
            case_results.append(result)

        passed = sum(1 for c in case_results if c.passed)
        score = passed / len(case_results) if case_results else 0.0
        logger.info(
            "CodeExecutor: model=%s pass_rate=%.4f passed=%d/%d",
            task_config.model,
            score,
            passed,
            len(test_cases),
        )
        return EvalResult(
            task_id=task_config.task_id,
            executor_key=self.name,
            model=task_config.model,
            level="L3",
            metric_name="code_pass_rate",
            metric_value=round(score, 4),
            cases=case_results,
            meta={"test_cases_total": len(test_cases), "test_cases_passed": passed},
        )

    def _load_test_cases(self, task_config: TaskConfig) -> list[CodeTestCase]:
        raw = task_config.params.get("test_cases", [])
        if raw:
            return [CodeTestCase(**t) if isinstance(t, dict) else t for t in raw]
        return self._default_test_cases()

    @staticmethod
    def _default_test_cases() -> list[CodeTestCase]:
        return [
            CodeTestCase(
                test_id="code-sort-function",
                prompt="Write a Python function that sorts a list of integers in ascending order.",
                language="python",
                expected_patterns=[r"def\s+\w+\s*\(", r"sort", r"return"],
                forbidden_patterns=[r"exec\s*\(", r"__import__"],
            ),
            CodeTestCase(
                test_id="code-fizzbuzz",
                prompt="Write a Python function fizzbuzz(n) that returns the FizzBuzz sequence up to n.",
                language="python",
                expected_patterns=[r"def\s+fizzbuzz", r"Fizz", r"Buzz"],
                forbidden_patterns=[r"exec\s*\("],
            ),
            CodeTestCase(
                test_id="code-error-handling",
                prompt="Write a Python function safe_divide(a, b) that handles division by zero.",
                language="python",
                expected_patterns=[
                    r"def\s+safe_divide",
                    r"try",
                    r"except",
                    r"ZeroDivision",
                ],
                forbidden_patterns=[r"exec\s*\("],
            ),
        ]

    async def _evaluate_code(
        self,
        test_case: CodeTestCase,
        task_config: TaskConfig,
    ) -> CaseResult:
        t0 = time.time()
        try:
            code = await self._generate_code(test_case, task_config)
            latency = (time.time() - t0) * 1000
            eval_result = self._eval_code_output(test_case, code)
            return CaseResult(
                input_text=test_case.prompt,
                expected=", ".join(test_case.expected_patterns),
                actual=code[:500],
                score=eval_result["score"],
                passed=eval_result["passed"],
                latency_ms=latency,
                meta={"test_id": test_case.test_id, **eval_result["details"]},
            )
        except Exception as e:
            logger.error("Code test %s failed: %s", test_case.test_id, e)
            return CaseResult(
                input_text=test_case.prompt,
                expected=", ".join(test_case.expected_patterns),
                actual=str(e),
                score=0.0,
                passed=False,
                latency_ms=(time.time() - t0) * 1000,
                meta={"test_id": test_case.test_id, "error": str(e)},
            )

    async def _generate_code(self, test_case: CodeTestCase, task_config: TaskConfig) -> str:
        messages = [
            {
                "role": "system",
                "content": f"Generate {test_case.language} code. Output only the code, no explanation.",
            },
            {"role": "user", "content": test_case.prompt},
        ]
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                json={
                    "model": task_config.model,
                    "messages": messages,
                    "max_tokens": task_config.params.get("max_tokens", 2048),
                    "temperature": task_config.params.get("temperature", 0.2),
                },
            )
            resp.raise_for_status()
            data = resp.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            return self._extract_code(content)

    @staticmethod
    def _extract_code(text: str) -> str:
        code_blocks = re.findall(r"```(?:\w+)?\s*\n(.*?)```", text, re.DOTALL)
        if code_blocks:
            return code_blocks[0].strip()
        return text.strip()

    @staticmethod
    def _eval_code_output(test_case: CodeTestCase, code: str) -> dict:
        details: dict = {"expected_matches": {}, "forbidden_violations": {}}
        expected_hits = 0
        for pattern in test_case.expected_patterns:
            try:
                match = bool(re.search(pattern, code))
            except re.error:
                match = pattern in code
            details["expected_matches"][pattern] = match
            if match:
                expected_hits += 1

        forbidden_hits = 0
        for pattern in test_case.forbidden_patterns:
            try:
                match = bool(re.search(pattern, code))
            except re.error:
                match = pattern in code
            details["forbidden_violations"][pattern] = match
            if match:
                forbidden_hits += 1

        total_expected = len(test_case.expected_patterns)
        score = expected_hits / total_expected if total_expected > 0 else 1.0
        if forbidden_hits > 0:
            score *= 0.5
        passed = score >= 0.6 and forbidden_hits == 0
        return {"score": score, "passed": passed, "details": details}
