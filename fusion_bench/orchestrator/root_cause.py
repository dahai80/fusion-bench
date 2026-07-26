# Importers/callers: orchestrator/pipeline.py calls analyze() after task failure; api/app.py can expose /tasks/{id}/root-cause.
# Affected API: adds RootCauseReport dataclass; no REST endpoint schema change (report embedded in task result).
# Data schemas: RootCauseReport (failure_category, root_cause, suggestions, confidence, related_errors).
# User instruction: "把所有没完全做完，没启动做，有差距的全部启动补齐" — P2-07 root cause analysis (FR-018).

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class RootCauseReport:
    failure_category: str = "unknown"
    root_cause: str = ""
    suggestions: list[str] = field(default_factory=list)
    confidence: float = 0.0
    related_errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "failure_category": self.failure_category,
            "root_cause": self.root_cause,
            "suggestions": self.suggestions,
            "confidence": self.confidence,
            "related_errors": self.related_errors,
            "metadata": self.metadata,
        }


_PATTERNS: list[dict[str, Any]] = [
    {
        "category": "timeout",
        "patterns": [r"timeout", r"timed?\s*out", r"deadline", r"exceeded.*time"],
        "root_cause": "Task execution exceeded the configured timeout limit.",
        "suggestions": [
            "Increase timeout_seconds in task config.",
            "Reduce max_samples to test fewer data points.",
            "Check if fusion-mlx is overloaded (run speed benchmark first).",
            "Consider using a smaller quantization variant.",
        ],
    },
    {
        "category": "connection_error",
        "patterns": [
            r"connection\s*(refused|error|reset|closed)",
            r"connect\s*call\s*failed",
            r"cannot\s*connect",
            r"network\s*is\s*unreachable",
        ],
        "root_cause": "Cannot connect to fusion-mlx HTTP API.",
        "suggestions": [
            "Verify fusion-mlx is running: curl http://localhost:11434/v1/models",
            "Check if the port is correct (default 11434).",
            "Restart fusion-mlx service.",
        ],
    },
    {
        "category": "model_not_found",
        "patterns": [
            r"model\s*not\s*found",
            r"404.*model",
            r"no\s*model\s*loaded",
            r"unknown\s*model",
            r"model\s*.*does\s*not\s*exist",
        ],
        "root_cause": "The requested model is not loaded in fusion-mlx.",
        "suggestions": [
            "Run: fusion-mlx load <model_name> to load the model.",
            "Check available models with: curl http://localhost:11434/v1/models",
            "Verify the model name spelling matches exactly.",
        ],
    },
    {
        "category": "out_of_memory",
        "patterns": [
            r"out\s*of\s*memory",
            r"oom",
            r"memory\s*allocat",
            r"cannot\s*allocate",
            r"metal.*memory",
            r"gpu.*memory",
            r"cuda.*oom",
        ],
        "root_cause": "GPU/Metal memory exhausted during inference.",
        "suggestions": [
            "Switch to a quantized model variant (e.g., -mxfp4 or -q4).",
            "Reduce batch_size in task parameters.",
            "Close other GPU-intensive applications.",
            "Use a smaller model if available.",
        ],
    },
    {
        "category": "circuit_breaker_open",
        "patterns": [r"circuit\s*breaker\s*open", r"circuit\s*open"],
        "root_cause": "Circuit breaker opened due to repeated failures for this executor.",
        "suggestions": [
            "Investigate root cause of previous failures first.",
            "Reset circuit breaker: pipeline.circuit_breaker.reset('<executor_key>').",
            "Increase circuit_breaker.failure_threshold if transient failures are expected.",
        ],
    },
    {
        "category": "executor_not_found",
        "patterns": [
            r"unknown\s*executor",
            r"executor.*not\s*found",
            r"key\s*error.*executor",
        ],
        "root_cause": "The specified executor plugin is not registered.",
        "suggestions": [
            "Check available executors: fusion-bench list-executors",
            "Verify the executor_key spelling in task config.",
            "Install missing dependencies for the executor.",
        ],
    },
    {
        "category": "dataset_error",
        "patterns": [
            r"dataset.*not\s*found",
            r"failed\s*to\s*load\s*dataset",
            r"no\s*dataset_path",
            r"huggingface.*error",
        ],
        "root_cause": "Failed to load the evaluation dataset.",
        "suggestions": [
            "Check dataset name and verify it exists on HuggingFace.",
            "Set HF_ENDPOINT=https://hf-mirror.com for mirror access.",
            "Download dataset manually: huggingface-cli download <dataset>.",
        ],
    },
    {
        "category": "rate_limit",
        "patterns": [r"rate\s*limit", r"429", r"too\s*many\s*requests", r"throttl"],
        "root_cause": "API rate limit exceeded on inference endpoint.",
        "suggestions": [
            "Reduce max_concurrent in pipeline config.",
            "Add delay between requests in task parameters.",
            "Check fusion-mlx rate limiting configuration.",
        ],
    },
]


def analyze(
    errors: list[str],
    executor_key: str = "",
    metric_value: float = 0.0,
    metric_name: str = "",
) -> RootCauseReport:
    if not errors:
        return RootCauseReport(
            failure_category="none",
            root_cause="No errors detected.",
            suggestions=[],
            confidence=1.0,
        )

    error_text = " ".join(str(e) for e in errors).lower()

    best_match: dict[str, Any] | None = None
    best_count = 0

    for pattern_def in _PATTERNS:
        match_count = 0
        for pat in pattern_def["patterns"]:
            if re.search(pat, error_text):
                match_count += 1
        if match_count > best_count:
            best_count = match_count
            best_match = pattern_def

    if best_match:
        confidence = min(0.95, 0.5 + best_count * 0.15)
        suggestions = list(best_match["suggestions"])

        if metric_name and metric_value == 0.0:
            suggestions.append(f"Metric '{metric_name}' is zero — verify the metric collection logic.")

        return RootCauseReport(
            failure_category=best_match["category"],
            root_cause=best_match["root_cause"],
            suggestions=suggestions,
            confidence=confidence,
            related_errors=errors[:5],
            metadata={
                "executor_key": executor_key,
                "metric_name": metric_name,
                "metric_value": metric_value,
            },
        )

    return RootCauseReport(
        failure_category="unclassified",
        root_cause=f"Unclassified failure in executor '{executor_key}': {errors[0][:200]}",
        suggestions=[
            "Check fusion-mlx logs for more detail.",
            "Run the task with verbose logging: --log-level DEBUG.",
            "Report this error pattern for future classification.",
        ],
        confidence=0.2,
        related_errors=errors[:5],
        metadata={
            "executor_key": executor_key,
            "metric_name": metric_name,
            "metric_value": metric_value,
        },
    )
