"""Tests for DSL eval executor (AST-based safe evaluation, #20)."""

from __future__ import annotations

import pytest

from fusion_bench.checkers.dsl_eval_executor import DSLEvalExecutor


@pytest.fixture
def executor():
    return DSLEvalExecutor()


@pytest.fixture
def params():
    return {
        "base_area": {"label": "底面积", "value": 12.0, "unit": "cm²"},
        "height": {"label": "高", "value": 5.0, "unit": "cm"},
        "radius": {"label": "半径", "value": 3.0, "unit": "cm"},
    }


class TestSafeArith:
    def test_simple_addition(self, executor):
        assert executor.execute_expr("1 + 2", {}, {}) == 3.0

    def test_operator_precedence(self, executor):
        assert executor.execute_expr("2 + 3 * 4", {}, {}) == 14.0

    def test_parentheses(self, executor):
        assert executor.execute_expr("(2 + 3) * 4", {}, {}) == 20.0

    def test_power(self, executor):
        assert executor.execute_expr("2 ** 3", {}, {}) == 8.0

    def test_division(self, executor):
        assert executor.execute_expr("10 / 4", {}, {}) == 2.5

    def test_unary_minus(self, executor):
        assert executor.execute_expr("-5 + 10", {}, {}) == 5.0

    def test_floats(self, executor):
        assert executor.execute_expr("3.14 * 2", {}, {}) == pytest.approx(6.28)


class TestParamSubstitution:
    def test_param_attribute(self, executor, params):
        assert executor.execute_expr("params.base_area * params.height", params, {}) == 60.0

    def test_param_single(self, executor, params):
        assert executor.execute_expr("params.radius", params, {}) == 3.0

    def test_param_in_expression(self, executor, params):
        assert executor.execute_expr("params.base_area + 10", params, {}) == 22.0

    def test_undefined_param(self, executor, params):
        with pytest.raises(ValueError, match="undefined parameter"):
            executor.execute_expr("params.nonexistent", params, {})


class TestResultsSubstitution:
    def test_results_index(self, executor):
        step_values = {1: 60.0}
        assert executor.execute_expr("results[1] * 2", {}, step_values) == 120.0

    def test_results_out_of_order(self, executor):
        with pytest.raises(ValueError, match="not computed yet"):
            executor.execute_expr("results[5]", {}, {1: 10.0})


class TestAllowedFunctions:
    def test_abs(self, executor):
        assert executor.execute_expr("abs(-5)", {}, {}) == 5.0

    def test_round(self, executor):
        assert executor.execute_expr("round(3.7)", {}, {}) == 4.0

    def test_min(self, executor):
        assert executor.execute_expr("min(1, 2, 3)", {}, {}) == 1.0

    def test_max(self, executor):
        assert executor.execute_expr("max(1, 2, 3)", {}, {}) == 3.0


class TestSecurityRejections:
    def test_attribute_access_rejected(self, executor):
        with pytest.raises(ValueError, match="disallowed attribute access"):
            executor.execute_expr("(1).__class__", {}, {})

    def test_dunder_access_rejected(self, executor, params):
        with pytest.raises(ValueError, match="underscore attribute"):
            executor.execute_expr("params.__class__", params, {})

    def test_unknown_function_rejected(self, executor):
        with pytest.raises(ValueError, match="only abs/round/min/max"):
            executor.execute_expr("open('x')", {}, {})

    def test_import_rejected(self, executor):
        with pytest.raises(ValueError):
            executor.execute_expr("__import__('os')", {}, {})

    def test_unknown_name_rejected(self, executor):
        with pytest.raises(ValueError, match="unknown name"):
            executor.execute_expr("foo + 1", {}, {})

    def test_bare_params_rejected(self, executor):
        with pytest.raises(ValueError, match="bare 'params'"):
            executor.execute_expr("params", {}, {})

    def test_bare_results_rejected(self, executor):
        with pytest.raises(ValueError, match="bare 'results'"):
            executor.execute_expr("results", {}, {})

    def test_empty_expr(self, executor):
        with pytest.raises(ValueError, match="empty"):
            executor.execute_expr("   ", {}, {})

    def test_syntax_error(self, executor):
        with pytest.raises(ValueError, match="syntax error"):
            executor.execute_expr("1 +", {}, {})

    def test_divide_by_zero(self, executor):
        with pytest.raises(ZeroDivisionError):
            executor.execute_expr("1 / 0", {}, {})


class TestPipelineExecution:
    def test_simple_pipeline(self, executor, params):
        pipeline = [
            {"step": 1, "eval": "params.base_area * params.height", "result_unit": "cm³"},
            {"step": 2, "eval": "results[1] / 3", "result_unit": "cm³"},
        ]
        result = executor.execute_pipeline(pipeline, params)
        assert result.success
        assert result.step_values[1] == 60.0
        assert result.step_values[2] == 20.0
        assert result.final_value == 20.0

    def test_pipeline_with_error(self, executor, params):
        pipeline = [
            {"step": 1, "eval": "params.base_area * params.height", "result_unit": "cm³"},
            {"step": 2, "eval": "1 / 0", "result_unit": "x"},
        ]
        result = executor.execute_pipeline(pipeline, params)
        assert not result.success
        assert len(result.errors) == 1
        assert "step 2" in result.errors[0]

    def test_empty_pipeline(self, executor):
        result = executor.execute_pipeline([], {})
        assert not result.success

    def test_pipeline_not_list(self, executor):
        result = executor.execute_pipeline("not a list", {})  # type: ignore[arg-type]
        assert not result.success
        assert "not a list" in result.errors[0]

    def test_final_value_is_last_step(self, executor, params):
        pipeline = [
            {"step": 1, "eval": "params.radius ** 2", "result_unit": "cm²"},
            {"step": 2, "eval": "results[1] * 3.14", "result_unit": "cm²"},
        ]
        result = executor.execute_pipeline(pipeline, params)
        assert result.final_value == pytest.approx(28.26)
