"""fusion-mlx chat model for langgraph (issue #53).

Minimal BaseChatModel over the fusion-mlx OpenAI-compatible API so the
langgraph arm runs on the identical model as the harness arm. Accumulates
provider-side usage (prompt/completion tokens) on every call — token cost is
measured from provider responses, never framework numbers.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import httpx
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

logger = logging.getLogger(__name__)


def mlx_api_key() -> str:
    import os

    for env in ("FUSION_CLIENT_KEY", "FUSION_MLX_API_KEY", "MLX_API_KEY"):
        if os.environ.get(env):
            return os.environ[env]
    try:
        from fusion_core.config import client_key

        return client_key()
    except Exception as e:
        logger.warning("no client key resolvable: %s; sending empty bearer", e)
        return ""


class MlxChatModel(BaseChatModel):
    """Sync chat model calling fusion-mlx /chat/completions directly."""

    model_name: str = "mlx-community--Qwen3.5-4B-MLX-4bit"
    base_url: str = "http://127.0.0.1:11434/v1"
    api_key: str = ""
    temperature: float = 0.0
    max_tokens: int = 1024
    tools_spec: list[Any] = Field(default_factory=list)
    # Usage accumulated from provider responses across the model instance.
    usage: dict[str, int] = Field(default_factory=dict)

    @property
    def _llm_type(self) -> str:
        return "fusion-mlx"

    def bind_tools(self, tools: Any, **kwargs: Any) -> MlxChatModel:
        from langchain_core.utils.function_calling import convert_to_openai_tool

        specs = [convert_to_openai_tool(t) for t in tools]
        logger.info("bind_tools: %d tool(s) %s", len(specs), [s["function"]["name"] for s in specs])
        return self.model_copy(update={"tools_spec": specs})

    def _convert(self, messages: list[BaseMessage]) -> list[dict]:
        out: list[dict] = []
        for m in messages:
            if isinstance(m, SystemMessage):
                out.append({"role": "system", "content": m.content})
            elif isinstance(m, ToolMessage):
                out.append({"role": "tool", "tool_call_id": m.tool_call_id, "content": str(m.content)})
            elif isinstance(m, AIMessage):
                entry: dict[str, Any] = {"role": "assistant", "content": m.content or ""}
                if m.tool_calls:
                    entry["tool_calls"] = [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {"name": tc["name"], "arguments": json.dumps(tc["args"])},
                        }
                        for tc in m.tool_calls
                    ]
                out.append(entry)
            else:
                out.append({"role": "user", "content": str(m.content)})
        return out

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": self._convert(messages),
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }
        if self.tools_spec:
            payload["tools"] = self.tools_spec
        # fusion-mlx force-caches T=0 completions; bypass keeps every call fresh.
        headers = {
            "Authorization": f"Bearer {self.api_key or mlx_api_key()}",
            "Content-Type": "application/json",
            "X-Cache": "bypass",
        }
        start = time.monotonic()
        # Upstream fusion-mlx#1665: deterministic prompt-dependent 500s that can
        # wedge the engine; retry with backoff instead of failing the episode.
        resp = None
        for attempt in range(1, 5):
            try:
                resp = httpx.post(f"{self.base_url}/chat/completions", json=payload, headers=headers, timeout=120.0)
                resp.raise_for_status()
                break
            except Exception as e:
                logger.warning("fusion-mlx call attempt %d failed: %s", attempt, e)
                if attempt == 4:
                    raise
                time.sleep(3.0 * attempt)
        assert resp is not None
        data = resp.json()
        wall = time.monotonic() - start
        choice = data["choices"][0]
        msg = choice["message"]
        usage = data.get("usage") or {}
        u = dict(self.usage)
        u["input_tokens"] = u.get("input_tokens", 0) + int(usage.get("prompt_tokens") or 0)
        u["output_tokens"] = u.get("output_tokens", 0) + int(usage.get("completion_tokens") or 0)
        u["llm_calls"] = u.get("llm_calls", 0) + 1
        u["wall_ms"] = u.get("wall_ms", 0) + int(wall * 1000)
        tool_calls = []
        for tc in msg.get("tool_calls") or []:
            try:
                args = json.loads(tc["function"]["arguments"])
            except (ValueError, KeyError) as e:
                logger.warning("bad tool_call arguments dropped: %s", e)
                continue
            tool_calls.append(
                {"name": tc["function"]["name"], "args": args, "id": tc.get("id") or "call_0", "type": "tool_call"}
            )
        ai = AIMessage(
            content=msg.get("content") or "",
            tool_calls=tool_calls,
            usage_metadata={
                "input_tokens": int(usage.get("prompt_tokens") or 0),
                "output_tokens": int(usage.get("completion_tokens") or 0),
                "total_tokens": int(usage.get("total_tokens") or 0),
            },
        )
        self.usage = u
        logger.info(
            "mlx call #%d in=%d out=%d tool_calls=%d wall=%.2fs",
            u["llm_calls"],
            u["input_tokens"],
            u["output_tokens"],
            len(tool_calls),
            wall,
        )
        return ChatResult(generations=[ChatGeneration(message=ai)])
