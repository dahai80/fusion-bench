"""DSL format checker — 4 hard-constraint checks for BNUP Dimension 1.

Checks (per spec §385-390):
1. Tag isolation — <thinking> + <dsl> both present, no illegal nesting.
2. JSON syntax — <dsl> content parses via json.loads().
3. Schema adherence — parsed dict passes fusion_core.validate_dsl().
4. Eval executable — pipeline eval expressions run via DSLEvalExecutor (AST).

Schema validation delegates to fusion_core.dsl_schema (single source of
truth upstream) — no local schema copy.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from fusion_core.dsl_schema import validate_dsl

from .dsl_eval_executor import DSLEvalExecutor, EvalResult
from .tag_extractor import extract_dsl, extract_thinking

logger = logging.getLogger(__name__)


@dataclass
class FormatReport:
    tag_isolation: bool = False
    json_syntax: bool = False
    schema_adherence: bool = False
    eval_executable: bool = False
    errors: list[str] = field(default_factory=list)
    dsl_dict: dict | None = None
    eval_result: EvalResult | None = None

    @property
    def all_passed(self) -> bool:
        return self.tag_isolation and self.json_syntax and self.schema_adherence and self.eval_executable

    @property
    def pass_count(self) -> int:
        return sum([self.tag_isolation, self.json_syntax, self.schema_adherence, self.eval_executable])

    def to_dict(self) -> dict:
        return {
            "tag_isolation": self.tag_isolation,
            "json_syntax": self.json_syntax,
            "schema_adherence": self.schema_adherence,
            "eval_executable": self.eval_executable,
            "all_passed": self.all_passed,
            "pass_count": self.pass_count,
            "errors": self.errors,
        }


class DSLFormatChecker:
    # 4-check format validator. Reuse DSLEvalExecutor for the eval check.

    def __init__(self, eval_executor: DSLEvalExecutor | None = None):
        self._eval_executor = eval_executor or DSLEvalExecutor()

    def check_tag_isolation(self, text: str) -> bool:
        if not isinstance(text, str):
            return False
        thinking = extract_thinking(text)
        dsl = extract_dsl(text)
        if thinking is None or dsl is None:
            logger.debug("tag_isolation fail: thinking=%s dsl=%s", thinking is not None, dsl is not None)
            return False
        if "<thinking>" in dsl or "<dsl>" in thinking:
            logger.debug("tag_isolation fail: illegal nesting")
            return False
        return True

    def check_json_syntax(self, text: str) -> tuple[bool, str]:
        dsl = extract_dsl(text)
        if dsl is None:
            return False, "<dsl> tag not found"
        try:
            json.loads(dsl)
            return True, ""
        except json.JSONDecodeError as e:
            return False, str(e)

    def check_schema(self, dsl_dict: dict) -> tuple[bool, list[str]]:
        if not isinstance(dsl_dict, dict):
            return False, ["dsl_dict is not a dict"]
        ok = validate_dsl(dsl_dict)
        if ok:
            return True, []
        return False, ["schema validation failed (see fusion_core.dsl_schema logs)"]

    def check_eval_executable(self, dsl_dict: dict) -> EvalResult:
        if not isinstance(dsl_dict, dict):
            return EvalResult(success=False, errors=["dsl_dict is not a dict"])
        pipeline = dsl_dict.get("pipeline")
        parameters = dsl_dict.get("parameters", {})
        if not isinstance(pipeline, list):
            return EvalResult(success=False, errors=["pipeline missing or not a list"])
        return self._eval_executor.execute_pipeline(pipeline, parameters)

    def run_all(self, text: str, ground_truth: str | float | None = None) -> FormatReport:
        report = FormatReport()
        if not isinstance(text, str):
            report.errors.append("text is not a string")
            return report
        report.tag_isolation = self.check_tag_isolation(text)
        json_ok, json_err = self.check_json_syntax(text)
        report.json_syntax = json_ok
        if not json_ok:
            report.errors.append(f"json_syntax: {json_err}")
            return report
        dsl_str = extract_dsl(text)
        try:
            dsl_dict = json.loads(dsl_str) if dsl_str else None
        except json.JSONDecodeError as e:
            report.errors.append(f"json parse: {e}")
            return report
        report.dsl_dict = dsl_dict
        schema_ok, schema_errs = self.check_schema(dsl_dict)
        report.schema_adherence = schema_ok
        if not schema_ok:
            report.errors.extend(schema_errs)
        eval_result = self.check_eval_executable(dsl_dict)
        report.eval_result = eval_result
        report.eval_executable = eval_result.success
        if not eval_result.success:
            report.errors.extend(eval_result.errors)
        logger.info(
            "format check: tag=%s json=%s schema=%s eval=%s",
            report.tag_isolation,
            report.json_syntax,
            report.schema_adherence,
            report.eval_executable,
        )
        return report
