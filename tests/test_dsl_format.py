"""Tests for DSL format checker (tag/JSON/schema/eval), #19."""

from __future__ import annotations

import json

from fusion_bench.checkers.dsl_format_checker import DSLFormatChecker, FormatReport
from fusion_bench.checkers.tag_extractor import extract_dsl, extract_thinking, extract_visual_state

VALID_PARAMS = {
    "base_area": {"label": "底面积", "value": 12.0, "unit": "cm²"},
    "height": {"label": "高", "value": 5.0, "unit": "cm"},
}

VALID_DSL_DICT = {
    "meta": {
        "id": "cylinder-volume-01",
        "grade": 6,
        "topic": "圆柱体积",
        "visual_type": "geometry_2d",
        "fallback_type": "tape_diagram",
    },
    "parameters": VALID_PARAMS,
    "entities": [
        {"id": "cyl", "type": "cylinder", "label": "圆柱", "properties": {}},
    ],
    "pipeline": [
        {
            "step": 1,
            "title": "底面积乘高",
            "formula": "V = S × h",
            "eval": "params.base_area * params.height",
            "result_unit": "cm³",
            "visual_state": {"progress_range": [0.0, 0.5], "active_entities": ["cyl"], "action": "highlight"},
        },
        {
            "step": 2,
            "title": "最终体积",
            "formula": "V",
            "eval": "results[1]",
            "result_unit": "cm³",
            "visual_state": {"progress_range": [0.5, 1.0], "active_entities": ["cyl"], "action": "reveal"},
        },
    ],
}

VALID_OUTPUT = f"""<thinking>
分析：圆柱体积 = 底面积 × 高。
</thinking>
<dsl>
{json.dumps(VALID_DSL_DICT, ensure_ascii=False)}
</dsl>"""


class TestTagExtractor:
    def test_extract_thinking(self):
        text = "<thinking>hello world</thinking>"
        assert extract_thinking(text) == "hello world"

    def test_extract_thinking_multiline(self):
        text = "<thinking>\nline1\nline2\n</thinking>"
        assert "line1" in extract_thinking(text)

    def test_extract_dsl(self):
        text = '<dsl>{"a": 1}</dsl>'
        assert extract_dsl(text) == '{"a": 1}'

    def test_extract_missing(self):
        assert extract_thinking("no tags here") is None
        assert extract_dsl("no tags here") is None

    def test_extract_visual_state(self):
        text = "<visual_state>[0, 0.5]</visual_state>"
        assert extract_visual_state(text) == "[0, 0.5]"

    def test_non_string(self):
        assert extract_thinking(None) is None  # type: ignore[arg-type]


class TestTagIsolation:
    def test_both_present(self):
        checker = DSLFormatChecker()
        assert checker.check_tag_isolation(VALID_OUTPUT)

    def test_missing_thinking(self):
        checker = DSLFormatChecker()
        text = '<dsl>{"a": 1}</dsl>'
        assert not checker.check_tag_isolation(text)

    def test_missing_dsl(self):
        checker = DSLFormatChecker()
        text = "<thinking>only thinking</thinking>"
        assert not checker.check_tag_isolation(text)

    def test_illegal_nesting(self):
        checker = DSLFormatChecker()
        text = "<thinking>has <dsl> inside</thinking>\n<dsl>x</dsl>"
        assert not checker.check_tag_isolation(text)


class TestJsonSyntax:
    def test_valid_json(self):
        checker = DSLFormatChecker()
        ok, err = checker.check_json_syntax(VALID_OUTPUT)
        assert ok
        assert err == ""

    def test_bad_json(self):
        checker = DSLFormatChecker()
        text = "<dsl>{bad json}</dsl>"
        ok, err = checker.check_json_syntax(text)
        assert not ok
        assert err

    def test_no_dsl_tag(self):
        checker = DSLFormatChecker()
        ok, err = checker.check_json_syntax("no dsl")
        assert not ok
        assert "not found" in err


class TestSchemaAdherence:
    def test_valid_schema(self):
        checker = DSLFormatChecker()
        ok, errs = checker.check_schema(VALID_DSL_DICT)
        assert ok
        assert errs == []

    def test_missing_required_field(self):
        checker = DSLFormatChecker()
        bad = {"meta": {}, "parameters": {}, "entities": []}
        ok, errs = checker.check_schema(bad)
        assert not ok

    def test_non_dict(self):
        checker = DSLFormatChecker()
        ok, errs = checker.check_schema("not a dict")  # type: ignore[arg-type]
        assert not ok


class TestRunAll:
    def test_well_formed(self):
        checker = DSLFormatChecker()
        report = checker.run_all(VALID_OUTPUT)
        assert report.tag_isolation
        assert report.json_syntax
        assert report.schema_adherence
        assert report.eval_executable
        assert report.all_passed
        assert report.dsl_dict is not None
        assert report.eval_result is not None
        assert report.eval_result.success

    def test_missing_tag(self):
        checker = DSLFormatChecker()
        report = checker.run_all("no tags at all")
        assert not report.tag_isolation
        assert not report.all_passed

    def test_bad_json(self):
        checker = DSLFormatChecker()
        text = "<thinking>ok</thinking>\n<dsl>{bad}</dsl>"
        report = checker.run_all(text)
        assert report.tag_isolation
        assert not report.json_syntax
        assert not report.all_passed

    def test_schema_fail_blocks_eval(self):
        checker = DSLFormatChecker()
        dsl_dict = {"meta": {}, "parameters": {}, "entities": [], "pipeline": []}
        text = f"<thinking>x</thinking>\n<dsl>{json.dumps(dsl_dict)}</dsl>"
        report = checker.run_all(text)
        assert report.json_syntax
        assert not report.schema_adherence

    def test_non_string_input(self):
        checker = DSLFormatChecker()
        report = checker.run_all(None)  # type: ignore[arg-type]
        assert not report.all_passed
        assert "not a string" in report.errors[0]


class TestFormatReport:
    def test_pass_count(self):
        report = FormatReport(tag_isolation=True, json_syntax=True, schema_adherence=False, eval_executable=True)
        assert report.pass_count == 3
        assert not report.all_passed

    def test_all_passed_true(self):
        report = FormatReport(tag_isolation=True, json_syntax=True, schema_adherence=True, eval_executable=True)
        assert report.all_passed
        assert report.pass_count == 4

    def test_to_dict(self):
        report = FormatReport(tag_isolation=True)
        d = report.to_dict()
        assert d["tag_isolation"] is True
        assert d["all_passed"] is False
        assert d["pass_count"] == 1
