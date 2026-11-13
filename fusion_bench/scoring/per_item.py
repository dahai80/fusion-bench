"""Per-item programmatic scoring (#44).

Synchronous, deterministic scoring of a single (input, completion) pair —
built for GRPO reward callbacks that need sub-second verdicts without the
task submission + poll round-trip. No task record, no trace store write.

Expected-answer resolution order:
    1. explicit `expected` argument
    2. `params.expected`
    3. `task` name -> lm-eval task YAML -> dataset ground truth matched by
       formatted prompt (looked up once, cached in-process)

Match rule mirrors LMEvalTaskRunner: normalized equality, then normalized
substring containment. Optional answer extraction (boxed / last_number)
runs on the completion before matching.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

_TARGET_CACHE: dict[tuple[str, str], dict[str, str]] = {}
_CACHE_MAX = 32

_BOXED_RE = re.compile(r"\\boxed\{([^{}]+)\}")
_LAST_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


def extract_answer(completion: str, mode: str = "") -> str:
    if mode == "boxed":
        matches = _BOXED_RE.findall(completion)
        return matches[-1].strip() if matches else ""
    if mode == "last_number":
        matches = _LAST_NUM_RE.findall(completion.replace(",", ""))
        return matches[-1] if matches else ""
    return completion


def _task_targets(task_name: str, tasks_dir: str = "") -> dict[str, str]:
    """input-prompt -> ground-truth target map for a lm-eval task, cached."""
    key = (task_name, tasks_dir)
    if key in _TARGET_CACHE:
        return _TARGET_CACHE[key]
    if len(_TARGET_CACHE) >= _CACHE_MAX:
        _TARGET_CACHE.clear()
        logger.info("Per-item target cache cleared (max %d tasks)", _CACHE_MAX)

    from ..engine.task_runner import LMEvalTaskRunner

    runner = LMEvalTaskRunner(tasks_dir=tasks_dir)
    task_data = runner._load_task(task_name)
    if not task_data:
        raise ValueError(f"Unknown task '{task_name}': no lm-eval YAML definition found")

    dataset_path = task_data.get("dataset_path", "")
    dataset_name = task_data.get("dataset_name", "")
    test_split = task_data.get("test_split", "test")
    doc_to_text = task_data.get("doc_to_text", "")
    doc_to_target = task_data.get("doc_to_target", "")
    if not dataset_path:
        raise ValueError(f"Task '{task_name}' has no dataset_path in its definition")

    from datasets import load_dataset

    ds = load_dataset(dataset_path, dataset_name, split=test_split)
    targets: dict[str, str] = {}
    for sample in ds:
        prompt = runner._format_prompt(sample, doc_to_text)
        target = runner._format_target(sample, doc_to_target)
        if prompt and target and prompt not in targets:
            targets[prompt] = target
    logger.info("Loaded %d ground-truth targets for task '%s'", len(targets), task_name)
    _TARGET_CACHE[key] = targets
    return targets


def score_item(
    item: dict,
    tasks_dir: str = "",
) -> dict:
    """Score one {task, input, completion, expected, params} dict.

    Returns {score: float, details: {...}}; never raises for item-level
    problems — failures come back as score 0.0 with details.error set.
    """
    task = str(item.get("task") or "")
    prompt = str(item.get("input") or "")
    completion = str(item.get("completion") or "")
    params = item.get("params") or {}
    expected = str(item.get("expected") or params.get("expected") or "")

    details: dict = {"task": task, "extract": "", "expected_source": ""}
    try:
        if not prompt:
            raise ValueError("input is required")
        if not completion:
            raise ValueError("completion is required")

        if expected:
            details["expected_source"] = "explicit"
        elif task:
            targets = _task_targets(task, tasks_dir)
            expected = targets.get(prompt, "")
            details["expected_source"] = "task_dataset"
            if not expected:
                raise ValueError(f"No ground truth found in task '{task}' for the given input")
        else:
            raise ValueError("either expected or task must be provided")

        extract_mode = str(params.get("extract") or "")
        candidate = extract_answer(completion, extract_mode)
        details["extract"] = extract_mode
        details["expected"] = expected[:200]

        from ..engine.task_runner import LMEvalTaskRunner

        pred_norm = LMEvalTaskRunner._normalize(candidate)
        target_norm = LMEvalTaskRunner._normalize(expected)
        matched = bool(pred_norm) and (pred_norm == target_norm or target_norm in pred_norm)
        details["matched_by"] = "exact" if pred_norm == target_norm else ("contains" if matched else "none")
        details["prediction"] = candidate[:200]
        score = 1.0 if matched else 0.0
        logger.info(
            "Per-item score: %.1f (task=%s extract=%s matched_by=%s)", score, task, extract_mode, details["matched_by"]
        )
        return {"score": score, "details": details}
    except Exception as e:
        logger.error("Per-item scoring failed: %s", e)
        details["error"] = str(e)
        return {"score": 0.0, "details": details}


def score_items(items: list[dict], tasks_dir: str = "") -> list[dict]:
    return [score_item(item, tasks_dir=tasks_dir) for item in items]
