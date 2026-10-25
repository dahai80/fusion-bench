"""Issue #29 — LoRA adapter passthrough to fusion-mlx chat/completions."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from fusion_bench.adapters.mlx_model import MLXModel
from fusion_bench.core.plugin_base import TaskConfig
from fusion_bench.engine.task_runner import LMEvalTaskRunner


class TestMLXModelAdapterPayload:
    async def test_chat_payload_includes_adapters(self):
        model = MLXModel(model="m", base_url="http://localhost:11434/v1", adapter_path="/adapters/000001")
        client = MagicMock()
        resp = MagicMock()
        resp.json.return_value = {"usage": {}, "choices": [{"message": {"content": "x"}}]}
        client.post = AsyncMock(return_value=resp)
        model._client = client
        await model._chat_completion(messages=[{"role": "user", "content": "hi"}])
        payload = client.post.call_args[1]["json"]
        assert payload["adapters"] == "/adapters/000001"

    async def test_chat_payload_no_adapters_when_empty(self):
        model = MLXModel(model="m", base_url="http://localhost:11434/v1")
        client = MagicMock()
        resp = MagicMock()
        resp.json.return_value = {"usage": {}, "choices": [{"message": {"content": "x"}}]}
        client.post = AsyncMock(return_value=resp)
        model._client = client
        await model._chat_completion(messages=[{"role": "user", "content": "hi"}])
        payload = client.post.call_args[1]["json"]
        assert "adapters" not in payload

    async def test_completion_payload_includes_adapters(self):
        model = MLXModel(model="m", base_url="http://localhost:11434/v1", adapter_path="/adapters/000002")
        client = MagicMock()
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"usage": {}, "choices": [{"text": "x"}]}
        client.post = AsyncMock(return_value=resp)
        model._client = client
        await model._completion(prompt="hi", max_tokens=1)
        payload = client.post.call_args[1]["json"]
        assert payload["adapters"] == "/adapters/000002"


class TestRunnerAndExecutorPassthrough:
    async def test_runner_forwards_adapter_to_model(self, tmp_path):
        task_dir = tmp_path / "mmlu"
        task_dir.mkdir()
        (task_dir / "mmlu.yaml").write_text("task: mmlu\ndataset_path: test\n")
        runner = LMEvalTaskRunner(model="m", tasks_dir=str(tmp_path), adapter_path="/adapters/000042")

        captured = {}

        class FakeModel:
            def __init__(self, **kwargs):
                captured.update(kwargs)

            async def generate_until(self, requests):
                return ["ans" for _ in requests]

            async def close(self):
                pass

            def get_usage_report(self):
                return {}

        with patch("fusion_bench.engine.task_runner.MLXModel", FakeModel):
            result = await runner.run_task("mmlu")
        assert captured.get("adapter_path") == "/adapters/000042"
        assert result["adapter_path"] == "/adapters/000042"

    async def test_executor_reads_params_key_fallback(self):
        from fusion_bench.executors.lm_harness_executor import LMHarnessExecutor

        executor = LMHarnessExecutor()
        config = TaskConfig(
            task_id="t",
            model="m",
            executor_key="lm_harness",
            params={"adapter_path": "/adapters/from-params"},
        )

        captured = {}

        class FakeRunner:
            def __init__(self, **kwargs):
                captured.update(kwargs)

            async def run_task(self, task_name, num_fewshot=0):
                return {"task": task_name, "metrics": {"accuracy": 0.5}, "results": []}

        with patch("fusion_bench.executors.lm_harness_executor.LMEvalTaskRunner", FakeRunner):
            result = await executor.run(config)
        assert captured.get("adapter_path") == "/adapters/from-params"
        assert result.meta["adapter_path"] == "/adapters/from-params"

    async def test_executor_top_level_field_wins(self):
        from fusion_bench.executors.lm_harness_executor import LMHarnessExecutor

        executor = LMHarnessExecutor()
        config = TaskConfig(
            task_id="t",
            model="m",
            executor_key="lm_harness",
            adapter_path="/adapters/top-level",
            params={"adapter_path": "/adapters/from-params"},
        )

        captured = {}

        class FakeRunner:
            def __init__(self, **kwargs):
                captured.update(kwargs)

            async def run_task(self, task_name, num_fewshot=0):
                return {"task": task_name, "metrics": {"accuracy": 0.5}, "results": []}

        with patch("fusion_bench.executors.lm_harness_executor.LMEvalTaskRunner", FakeRunner):
            await executor.run(config)
        assert captured.get("adapter_path") == "/adapters/top-level"

    def test_task_config_has_adapter_field(self):
        config = TaskConfig(task_id="t", model="m", executor_key="speed")
        assert config.adapter_path == ""


class TestAPIRequestField:
    def test_task_create_request_adapter_path(self):
        from fusion_bench.api.app import TaskCreateRequest

        req = TaskCreateRequest(model="m", adapter_path="/adapters/000123")
        assert req.adapter_path == "/adapters/000123"
        assert TaskCreateRequest(model="m").adapter_path == ""
