"""SSE real-time progress - Server-Sent Events for task monitoring.

Importers/callers: api/app.py /tasks/{id}/events endpoint uses EventSourceResponse.
Affected API: adds SSE stream endpoint; no schema changes.
Data schema: SSEEvent dataclass (event, data, id, retry); reuses existing task status.
User instruction: "把所有没完全做完，没启动做，有差距的全部启动补齐" (P1-7 SSE progress).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SSEEvent:
    event: str = "message"
    data: str = ""
    id: str = ""
    retry: int = 5000

    def encode(self) -> str:
        lines = []
        if self.event != "message":
            lines.append(f"event: {self.event}")
        if self.id:
            lines.append(f"id: {self.id}")
        if self.retry != 5000:
            lines.append(f"retry: {self.retry}")
        for line in self.data.split("\n"):
            lines.append(f"data: {line}")
        lines.append("")
        lines.append("")
        return "\n".join(lines)


class SSEProgressStream:
    """Manages SSE event streams for task progress."""

    def __init__(self):
        self._queues: dict[str, asyncio.Queue] = {}
        self._event_counter: int = 0

    def _get_queue(self, task_id: str) -> asyncio.Queue:
        if task_id not in self._queues:
            self._queues[task_id] = asyncio.Queue(maxsize=100)
        return self._queues[task_id]

    def emit(self, task_id: str, event_type: str, data: dict[str, Any]) -> None:
        self._event_counter += 1
        evt = SSEEvent(
            event=event_type,
            data=json.dumps(data, ensure_ascii=False),
            id=f"{task_id}-{self._event_counter}",
        )
        q = self._get_queue(task_id)
        try:
            q.put_nowait(evt)
        except asyncio.QueueFull:
            logger.warning("SSE queue full for task %s, dropping event", task_id)

    async def subscribe(self, task_id: str) -> AsyncIterator[str]:
        q = self._get_queue(task_id)
        yield SSEEvent(
            event="connected",
            data=json.dumps({"task_id": task_id, "ts": time.strftime("%H:%M:%S")}),
        ).encode()
        try:
            while True:
                try:
                    evt = await asyncio.wait_for(q.get(), timeout=30.0)
                    yield evt.encode()
                except TimeoutError:
                    yield SSEEvent(
                        event="heartbeat",
                        data=json.dumps({"ts": time.strftime("%H:%M:%S")}),
                    ).encode()
        except asyncio.CancelledError:
            pass
        finally:
            if task_id in self._queues and self._queues[task_id].empty():
                del self._queues[task_id]

    def cleanup(self, task_id: str) -> None:
        self._queues.pop(task_id, None)


_progress_stream = SSEProgressStream()


def get_progress_stream() -> SSEProgressStream:
    return _progress_stream
