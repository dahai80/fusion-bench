"""AST-based safe DSL pipeline evaluator — no eval()/exec().

Evaluates pipeline `eval` expressions like `params.base_area * params.height`
or `results[1] * (2/3)` by walking the AST and allowing only a closed set of
nodes. Any disallowed node (attribute access on non-params, unknown function
calls, dunder access, imports) raises ValueError — fail-closed per the
security constraint shared by agent/code/security executors.
"""

from __future__ import annotations

import ast
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

_ALLOWED_FUNCS = {"abs", "round", "min", "max"}

_ALLOWED_BINOPS = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
    ast.Pow: lambda a, b: a**b,
}


@dataclass
class EvalResult:
    success: bool
    final_value: float | None = None
    step_values: dict[int, float] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


class _SafeEvalVisitor(ast.NodeVisitor):
    # Evaluates one expression. params/results resolve against the context.

    def __init__(self, parameters: dict[str, Any], step_values: dict[int, float]):
        self.parameters = parameters
        self.step_values = step_values

    def visit_Constant(self, node: ast.Constant) -> float:
        if isinstance(node.value, bool):
            raise ValueError("bool literal not allowed")
        if not isinstance(node.value, int | float):
            raise ValueError(f"bad constant type: {type(node.value).__name__}")
        return float(node.value)

    def visit_BinOp(self, node: ast.BinOp) -> float:
        left = self.visit(node.left)
        right = self.visit(node.right)
        op_fn = _ALLOWED_BINOPS.get(type(node.op))
        if op_fn is None:
            raise ValueError(f"disallowed binary op: {type(node.op).__name__}")
        return op_fn(left, right)

    def visit_UnaryOp(self, node: ast.UnaryOp) -> float:
        operand = self.visit(node.operand)
        if isinstance(node.op, ast.USub):
            return -operand
        if isinstance(node.op, ast.UAdd):
            return +operand
        raise ValueError(f"disallowed unary op: {type(node.op).__name__}")

    def visit_Name(self, node: ast.Name) -> Any:
        # Bare params/results without subscript/attribute is invalid.
        if node.id in ("params", "results"):
            raise ValueError(f"bare '{node.id}' used without index/attribute")
        raise ValueError(f"unknown name: {node.id}")

    def visit_Attribute(self, node: ast.Attribute) -> float:
        # Only params.<name> allowed; reject all other attribute access
        # (blocks dunder walks like __class__, __import__).
        if not isinstance(node.value, ast.Name) or node.value.id != "params":
            raise ValueError(f"disallowed attribute access: {node.attr}")
        if node.attr.startswith("_"):
            raise ValueError(f"underscore attribute access blocked: {node.attr}")
        param = self.parameters.get(node.attr)
        if param is None:
            raise ValueError(f"undefined parameter: {node.attr}")
        value = param.get("value") if isinstance(param, dict) else param
        if not isinstance(value, int | float):
            raise ValueError(f"parameter '{node.attr}' value not numeric: {type(value).__name__}")
        return float(value)

    def visit_Subscript(self, node: ast.Subscript) -> float:
        # Only results[n] allowed (1-indexed step result).
        if not isinstance(node.value, ast.Name) or node.value.id != "results":
            raise ValueError("subscript only allowed on 'results'")
        idx = self.visit(node.slice)
        idx_int = int(idx)
        if idx_int not in self.step_values:
            raise ValueError(f"results[{idx_int}] not computed yet (step out of order?)")
        return self.step_values[idx_int]

    def visit_Call(self, node: ast.Call) -> float:
        if not isinstance(node.func, ast.Name) or node.func.id not in _ALLOWED_FUNCS:
            raise ValueError("only abs/round/min/max calls allowed")
        args = [self.visit(a) for a in node.args]
        if node.keywords:
            raise ValueError("keyword args not allowed in eval calls")
        fn = {
            "abs": abs,
            "round": lambda x, n=0: round(x, int(n)),
            "min": min,
            "max": max,
        }[node.func.id]
        return float(fn(*args))

    def generic_visit(self, node: ast.AST) -> Any:
        raise ValueError(f"disallowed AST node: {type(node).__name__}")


class DSLEvalExecutor:
    # Safe pipeline evaluator. No eval()/exec() — pure AST walk.

    def execute_expr(self, expr: str, parameters: dict[str, Any], step_values: dict[int, float]) -> float:
        if not isinstance(expr, str) or not expr.strip():
            raise ValueError("empty eval expression")
        try:
            tree = ast.parse(expr.strip(), mode="eval")
        except SyntaxError as e:
            raise ValueError(f"syntax error in eval: {e}") from e
        visitor = _SafeEvalVisitor(parameters, step_values)
        result = visitor.visit(tree.body)
        if not isinstance(result, int | float):
            raise ValueError(f"eval result not numeric: {type(result).__name__}")
        return float(result)

    def execute_pipeline(self, pipeline: list[dict], parameters: dict[str, Any]) -> EvalResult:
        step_values: dict[int, float] = {}
        errors: list[str] = []
        if not isinstance(pipeline, list):
            return EvalResult(success=False, errors=["pipeline is not a list"])
        for step in pipeline:
            if not isinstance(step, dict):
                errors.append(f"step is not a dict: {type(step).__name__}")
                continue
            step_no = step.get("step")
            eval_expr = step.get("eval", "")
            if not isinstance(step_no, int | float):
                errors.append(f"step missing numeric 'step' field: {step_no!r}")
                continue
            step_int = int(step_no)
            try:
                value = self.execute_expr(str(eval_expr), parameters, step_values)
                step_values[step_int] = value
                logger.debug("pipeline step %d eval = %s", step_int, value)
            except Exception as e:
                errors.append(f"step {step_int} eval failed: {e}")
                logger.warning("pipeline step %d eval failed: %s", step_int, e)
        final_value = step_values.get(int(pipeline[-1]["step"])) if pipeline and not errors else None
        success = not errors and bool(step_values)
        return EvalResult(
            success=success,
            final_value=final_value,
            step_values=step_values,
            errors=errors,
        )

    def compare_final(
        self,
        eval_result: EvalResult,
        ground_truth: float | int | str | None,
        tolerance: float = 1e-3,
    ) -> bool:
        # Compare the pipeline's final value against a ground-truth answer.
        # Returns False if eval failed, no final value, or ground truth absent.
        if not isinstance(eval_result, EvalResult) or not eval_result.success or eval_result.final_value is None:
            return False
        if ground_truth is None:
            return False
        try:
            gt = float(ground_truth)
        except (TypeError, ValueError) as e:
            logger.warning("compare_final: ground_truth not numeric: %s (%s)", ground_truth, e)
            return False
        return abs(eval_result.final_value - gt) <= tolerance
