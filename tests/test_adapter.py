"""Tests for Fusion-Bench MLX adapter and task runner."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from fusion_bench.adapters.mlx_model import MLXModel
from fusion_bench.engine.task_runner import LMEvalTaskRunner


class MockResponse:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json = json_data or {
            "choices": [{"message": {"content": "test response"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }
    def raise_for_status(self):
        pass
    def json(self):
        return self._json


class TestMLXModel:
    def test_init(self):
        model = MLXModel(model="test-model", base_url="http://localhost:11434/v1")
        assert model.model_name == "test-model"
        assert model.temperature == 0.0
        assert model.total_prompt_tokens == 0

    @pytest.mark.asyncio
    async def test_generate_until(self):
        model = MLXModel(base_url="http://localhost:11434/v1")
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=MockResponse())
        model._client = mock_client
        results = await model.generate_until([{"context": "hello", "until": [], "max_length": 50}])
        assert len(results) == 1
        assert "test response" in results[0]

    @pytest.mark.asyncio
    async def test_generate_until_with_stop(self):
        model = MLXModel(base_url="http://localhost:11434/v1")
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=MockResponse(json_data={
            "choices": [{"message": {"content": "hello world\nmore"}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 10},
        }))
        model._client = mock_client
        results = await model.generate_until([{"context": "hi", "until": ["\n"], "max_length": 50}])
        assert "\n" not in results[0]

    @pytest.mark.asyncio
    async def test_generate_until_error(self):
        model = MLXModel(base_url="http://localhost:11434/v1")
        mock_client = MagicMock()
        mock_client.post = AsyncMock(side_effect=RuntimeError("fail"))
        model._client = mock_client
        results = await model.generate_until([{"context": "hello", "until": [], "max_length": 50}])
        assert results[0] == ""

    @pytest.mark.asyncio
    async def test_loglikelihood(self):
        model = MLXModel(base_url="http://localhost:11434/v1")
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=MockResponse(json_data={
            "choices": [{"text": " answer", "logprobs": {"tokens": [" answer"], "token_logprobs": [-0.5]}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 1},
        }))
        model._client = mock_client
        results = await model.loglikelihood([("question", " answer")])
        assert len(results) == 1
        assert isinstance(results[0][0], float)

    @pytest.mark.asyncio
    async def test_loglikelihood_fallback(self):
        model = MLXModel(base_url="http://localhost:11434/v1")
        mock_client = MagicMock()
        mock_client.post = AsyncMock(side_effect=[
            RuntimeError("fail"),  # /v1/completions fails
            MockResponse(),  # /v1/chat/completions fallback
        ])
        model._client = mock_client
        results = await model.loglikelihood([("question", " answer")])
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_loglikelihood_rolling(self):
        model = MLXModel(base_url="http://localhost:11434/v1")
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=MockResponse(json_data={
            "choices": [{"text": "test", "logprobs": {"tokens": ["test"], "token_logprobs": [-0.3]}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 1},
        }))
        model._client = mock_client
        results = await model.loglikelihood_rolling(["test text"])
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_tok_encode_decode(self):
        model = MLXModel()
        tokens = model.tok_encode("hello world")
        assert len(tokens) >= 1
        decoded = model.tok_decode(tokens)
        assert "tokens" in decoded

    @pytest.mark.asyncio
    async def test_get_usage_report(self):
        model = MLXModel()
        model.total_prompt_tokens = 100
        model.total_completion_tokens = 50
        report = model.get_usage_report()
        assert report["total_tokens"] == 150

    @pytest.mark.asyncio
    async def test_close(self):
        model = MLXModel()
        _ = model.client
        await model.close()
        assert model._client is None

    @pytest.mark.asyncio
    async def test_extract_content(self):
        data = {"choices": [{"message": {"content": "hello"}}]}
        assert MLXModel._extract_content(data) == "hello"
        assert MLXModel._extract_content({}) == ""

    @pytest.mark.asyncio
    async def test_extract_loglikelihood(self):
        data = {"choices": [{"logprobs": {"tokens": ["a", "b"], "token_logprobs": [-0.5, -0.3]}}]}
        ll = MLXModel._extract_loglikelihood(data, "ab")
        assert ll < 0
        assert MLXModel._extract_loglikelihood({}, "x") < 0


class TestLMEvalTaskRunner:
    def test_list_tasks_no_dir(self):
        runner = LMEvalTaskRunner(tasks_dir="/nonexistent")
        tasks = runner.list_tasks()
        assert tasks == []

    def test_init(self):
        runner = LMEvalTaskRunner(model="test-model")
        assert runner.model_name == "test-model"

    @pytest.mark.asyncio
    async def test_load_task_not_found(self):
        runner = LMEvalTaskRunner(tasks_dir="/nonexistent")
        result = await runner.run_task("nonexistent_task")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_format_prompt(self):
        sample = {"question": "What is 2+2?", "answer": "4"}
        prompt = LMEvalTaskRunner._format_prompt(sample, "{question}")
        assert prompt == "What is 2+2?"
        prompt2 = LMEvalTaskRunner._format_prompt(sample, "")
        assert prompt2 == "What is 2+2?"

    @pytest.mark.asyncio
    async def test_format_target(self):
        sample = {"answer": "4", "label": "B"}
        target = LMEvalTaskRunner._format_target(sample, "{answer}")
        assert target == "4"
        target2 = LMEvalTaskRunner._format_target(sample, "")
        assert target2 == "4"

    @pytest.mark.asyncio
    async def test_format_target_fallback(self):
        # "text" is not in the fallback chain, so returns empty string
        sample = {"text": "hello"}
        assert LMEvalTaskRunner._format_target(sample, "") == ""

    @pytest.mark.asyncio
    async def test_normalize(self):
        assert LMEvalTaskRunner._normalize("  Hello, World!  ") == "hello world"
        assert LMEvalTaskRunner._normalize("A") == "a"
        assert LMEvalTaskRunner._normalize("") == ""

    @pytest.mark.asyncio
    async def test_run_benchmark(self):
        runner = LMEvalTaskRunner(tasks_dir="/nonexistent")
        results = await runner.run_benchmark(["task1", "task2"])
        assert len(results) == 2
        for r in results:
            assert "error" in r