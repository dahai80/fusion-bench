"""L4 Artifact evaluation executor - evaluates generated artifacts (text, config, JSON, YAML).

Importers/callers: executors/__init__.py register_all() imports and registers ArtifactExecutor.
Affected API: calls POST /chat/completions on fusion-mlx; no new public API surface.
Data schemas: ArtifactCriteria dataclass (name, description, weight, auto_check); ArtifactTestCase (test_id, artifact_type, prompt, criteria, min_length); EvalResult from plugin_base.
User instruction: "把所有没完全做完，没启动做，有差距的全部启动补齐" (P2-11).
"""

from __future__ import annotations

import json
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
class ArtifactCriteria:
    name: str
    description: str
    weight: float = 1.0
    auto_check: str = ""


@dataclass
class ArtifactTestCase:
    test_id: str
    artifact_type: str
    prompt: str
    criteria: list[ArtifactCriteria] = field(default_factory=list)
    min_length: int = 50


class ArtifactExecutor(ExecutorPlugin):
    """L4 Artifact layer executor - evaluates generated artifact quality."""

    name = "artifact"
    executor_type = ExecutorType.ARTIFACT

    def __init__(self, base_url: str = "http://localhost:11434/v1"):
        self.base_url = base_url.rstrip("/")

    def is_available(self) -> bool:
        try:
            resp = httpx.get(f"{self.base_url}/models", timeout=5.0)
            return resp.status_code == 200
        except Exception:
            return False

    async def run(self, task_config: TaskConfig) -> EvalResult:
        logger.info("ArtifactExecutor: running artifact eval for model=%s", task_config.model)
        test_cases = self._load_test_cases(task_config)
        if not test_cases:
            return EvalResult(
                score=0.0,
                metrics={"test_cases_total": 0},
                details={"error": "No artifact test cases found"},
            )

        case_results: list[CaseResult] = []
        for tc in test_cases:
            result = await self._evaluate_artifact(tc, task_config)
            case_results.append(result)

        passed = sum(1 for c in case_results if c.passed)
        score = passed / len(case_results) if case_results else 0.0
        return EvalResult(
            score=score,
            metrics={"test_cases_total": len(test_cases), "test_cases_passed": passed},
            case_results=case_results,
        )

    def _load_test_cases(self, task_config: TaskConfig) -> list[ArtifactTestCase]:
        raw = task_config.params.get("test_cases", [])
        if raw:
            cases = []
            for t in raw:
                if isinstance(t, dict):
                    criteria = t.pop("criteria", [])
                    criteria_objs = [ArtifactCriteria(**c) if isinstance(c, dict) else c for c in criteria]
                    cases.append(ArtifactTestCase(criteria=criteria_objs, **t))
                else:
                    cases.append(t)
            return cases
        return self._default_test_cases()

    @staticmethod
    def _default_test_cases() -> list[ArtifactTestCase]:
        return [
            ArtifactTestCase(
                test_id="artifact-json-config",
                artifact_type="json",
                prompt="Generate a JSON configuration for a web server with host, port, and logging settings.",
                criteria=[
                    ArtifactCriteria(
                        name="valid_json",
                        description="Output is valid JSON",
                        auto_check="json_valid",
                    ),
                    ArtifactCriteria(
                        name="has_host",
                        description="Contains host field",
                        auto_check="contains:host",
                    ),
                    ArtifactCriteria(
                        name="has_port",
                        description="Contains port field",
                        auto_check="contains:port",
                    ),
                ],
                min_length=30,
            ),
            ArtifactTestCase(
                test_id="artifact-markdown-readme",
                artifact_type="markdown",
                prompt="Write a README.md for a Python CLI tool called 'mytool'.",
                criteria=[
                    ArtifactCriteria(
                        name="has_heading",
                        description="Has markdown heading",
                        auto_check=r"#",
                    ),
                    ArtifactCriteria(
                        name="has_install",
                        description="Has install instructions",
                        auto_check="contains:install",
                    ),
                    ArtifactCriteria(
                        name="min_len",
                        description="Sufficient length",
                        auto_check="min_length:100",
                    ),
                ],
                min_length=100,
            ),
            ArtifactTestCase(
                test_id="artifact-yaml-compose",
                artifact_type="yaml",
                prompt="Generate a docker-compose.yml for a web app with a redis service.",
                criteria=[
                    ArtifactCriteria(
                        name="has_services",
                        description="Has services key",
                        auto_check="contains:services",
                    ),
                    ArtifactCriteria(
                        name="has_redis",
                        description="Has redis service",
                        auto_check="contains:redis",
                    ),
                ],
                min_length=50,
            ),
        ]

    async def _evaluate_artifact(
        self,
        test_case: ArtifactTestCase,
        task_config: TaskConfig,
    ) -> CaseResult:
        t0 = time.time()
        try:
            artifact = await self._generate_artifact(test_case, task_config)
            latency = (time.time() - t0) * 1000
            eval_result = self._eval_artifact(test_case, artifact)
            return CaseResult(
                input_text=test_case.prompt,
                expected=f"{test_case.artifact_type} artifact",
                actual=artifact[:500],
                score=eval_result["score"],
                passed=eval_result["passed"],
                latency_ms=latency,
                meta={"test_id": test_case.test_id, **eval_result["details"]},
            )
        except Exception as e:
            logger.error("Artifact test %s failed: %s", test_case.test_id, e)
            return CaseResult(
                input_text=test_case.prompt,
                expected=f"{test_case.artifact_type} artifact",
                actual=str(e),
                score=0.0,
                passed=False,
                latency_ms=(time.time() - t0) * 1000,
                meta={"test_id": test_case.test_id, "error": str(e)},
            )

    async def _generate_artifact(self, test_case: ArtifactTestCase, task_config: TaskConfig) -> str:
        messages = [
            {
                "role": "system",
                "content": f"Generate a {test_case.artifact_type} artifact. Output only the artifact content.",
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
                    "temperature": task_config.params.get("temperature", 0.3),
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("choices", [{}])[0].get("message", {}).get("content", "")

    def _eval_artifact(self, test_case: ArtifactTestCase, artifact: str) -> dict:
        details: dict = {"criteria_results": {}}
        weighted_score = 0.0
        total_weight = 0.0

        length_pass = len(artifact) >= test_case.min_length

        for criterion in test_case.criteria:
            check_result = self._check_criterion(criterion, artifact)
            details["criteria_results"][criterion.name] = check_result
            weighted_score += check_result * criterion.weight
            total_weight += criterion.weight

        score = weighted_score / total_weight if total_weight > 0 else 0.0
        if not length_pass:
            score *= 0.8
        passed = score >= 0.6 and length_pass
        details["min_length_check"] = length_pass
        return {"score": score, "passed": passed, "details": details}

    @staticmethod
    def _check_criterion(criterion: ArtifactCriteria, artifact: str) -> float:
        check = criterion.auto_check
        if not check:
            return 1.0 if len(artifact) > 10 else 0.0

        if check == "json_valid":
            try:
                json.loads(artifact)
                return 1.0
            except json.JSONDecodeError:
                try:
                    json.loads(artifact[artifact.index("{") : artifact.rindex("}") + 1])
                    return 0.8
                except (ValueError, json.JSONDecodeError):
                    return 0.0

        if check.startswith("min_length:"):
            try:
                min_len = int(check.split(":")[1])
                return 1.0 if len(artifact) >= min_len else 0.0
            except (ValueError, IndexError):
                return 0.0

        if check.startswith("contains:"):
            text = check.split(":", 1)[1]
            return 1.0 if text.lower() in artifact.lower() else 0.0

        try:
            return 1.0 if re.search(check, artifact) else 0.0
        except re.error:
            return 1.0 if check in artifact else 0.0
