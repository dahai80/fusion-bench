"""Distributed execution interface - ABC for multi-node task distribution.

Importers/callers: orchestrator/pipeline.py can optionally inject a TaskDistributor.
Affected API: TaskDistributor ABC (dispatch/collect/status/cancel/list_nodes); no REST endpoints added.
Data schema: DistributedTask (task_id, node_id, status, result, error); NodeInfo (node_id, address, capacity, load, healthy).
User instruction: "把所有没完全做完，没启动做，有差距的全部启动补齐" (P1-2 distributed execution interface).
"""

from __future__ import annotations

import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


class DistributedStatus(StrEnum):
    DISPATCHED = "dispatched"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


@dataclass
class DistributedTask:
    task_id: str
    node_id: str = ""
    status: DistributedStatus = DistributedStatus.DISPATCHED
    result: dict[str, Any] = field(default_factory=dict)
    error: str = ""


@dataclass
class NodeInfo:
    node_id: str
    address: str
    capacity: int = 4
    current_load: int = 0
    healthy: bool = True


class TaskDistributor(ABC):
    """Abstract base class for distributed task execution."""

    @abstractmethod
    async def dispatch(self, task_config: dict[str, Any], preferred_node: str = "") -> DistributedTask: ...

    @abstractmethod
    async def collect(self, task_id: str, timeout: float = 600.0) -> DistributedTask: ...

    @abstractmethod
    async def status(self, task_id: str) -> DistributedTask | None: ...

    @abstractmethod
    async def list_nodes(self) -> list[NodeInfo]: ...

    @abstractmethod
    async def cancel(self, task_id: str) -> bool: ...


class LocalDistributor(TaskDistributor):
    """Local-only distributor - runs tasks on the same node (default fallback)."""

    def __init__(self):
        self._tasks: dict[str, DistributedTask] = {}
        self._node = NodeInfo(node_id="local", address="localhost")

    async def dispatch(self, task_config: dict[str, Any], preferred_node: str = "") -> DistributedTask:
        task_id = task_config.get("task_id", "local-0")
        dt = DistributedTask(task_id=task_id, node_id="local", status=DistributedStatus.DISPATCHED)
        self._tasks[task_id] = dt
        logger.info("LocalDistributor: dispatched %s", task_id)
        return dt

    async def collect(self, task_id: str, timeout: float = 600.0) -> DistributedTask:
        return self._tasks.get(
            task_id,
            DistributedTask(task_id=task_id, status=DistributedStatus.FAILED, error="Not found"),
        )

    async def status(self, task_id: str) -> DistributedTask | None:
        return self._tasks.get(task_id)

    async def list_nodes(self) -> list[NodeInfo]:
        return [self._node]

    async def cancel(self, task_id: str) -> bool:
        if task_id in self._tasks:
            self._tasks[task_id].status = DistributedStatus.FAILED
            self._tasks[task_id].error = "Cancelled"
            return True
        return False


class RemoteDistributor(TaskDistributor):
    """Distributes tasks to remote fusion-bench instances via HTTP API.

    Uses the fusion-bench REST API (/api/v1/tasks) on remote nodes
    to dispatch, monitor, and collect results.
    """

    def __init__(self, nodes: list[dict[str, str]] | None = None, timeout: float = 600.0):
        self._nodes: dict[str, NodeInfo] = {}
        self._tasks: dict[str, DistributedTask] = {}
        self._timeout = timeout
        self._round_robin_idx = 0

        for node_cfg in nodes or []:
            node_id = node_cfg.get("node_id", node_cfg.get("address", "unknown"))
            self._nodes[node_id] = NodeInfo(
                node_id=node_id,
                address=node_cfg.get("address", ""),
                capacity=int(node_cfg.get("capacity", 4)),
            )

    def add_node(self, node_id: str, address: str, capacity: int = 4) -> None:
        self._nodes[node_id] = NodeInfo(node_id=node_id, address=address, capacity=capacity)
        logger.info("RemoteDistributor: added node %s at %s", node_id, address)

    def remove_node(self, node_id: str) -> None:
        self._nodes.pop(node_id, None)
        logger.info("RemoteDistributor: removed node %s", node_id)

    def _select_node(self, preferred_node: str = "") -> NodeInfo | None:
        if preferred_node and preferred_node in self._nodes:
            node = self._nodes[preferred_node]
            if node.healthy and node.current_load < node.capacity:
                return node

        node_list = list(self._nodes.values())
        if not node_list:
            return None

        for _ in range(len(node_list)):
            node = node_list[self._round_robin_idx % len(node_list)]
            self._round_robin_idx += 1
            if node.healthy and node.current_load < node.capacity:
                return node

        return None

    async def dispatch(self, task_config: dict[str, Any], preferred_node: str = "") -> DistributedTask:
        import httpx

        task_id = task_config.get("task_id", f"remote-{uuid.uuid4().hex[:6]}")
        node = self._select_node(preferred_node)

        if not node:
            dt = DistributedTask(
                task_id=task_id,
                status=DistributedStatus.FAILED,
                error="No healthy remote nodes available",
            )
            self._tasks[task_id] = dt
            logger.error("RemoteDistributor: no nodes for task %s", task_id)
            return dt

        dt = DistributedTask(
            task_id=task_id,
            node_id=node.node_id,
            status=DistributedStatus.DISPATCHED,
        )
        self._tasks[task_id] = dt
        node.current_load += 1

        try:
            url = f"{node.address.rstrip('/')}/api/v1/tasks"
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(url, json=task_config)
                if resp.status_code in (200, 201):
                    data = resp.json()
                    dt.result = data
                    dt.status = DistributedStatus.RUNNING
                    logger.info(
                        "RemoteDistributor: dispatched %s to %s (%s)",
                        task_id,
                        node.node_id,
                        url,
                    )
                else:
                    dt.status = DistributedStatus.FAILED
                    dt.error = f"Remote API returned {resp.status_code}: {resp.text[:200]}"
                    node.current_load = max(0, node.current_load - 1)
                    logger.error("RemoteDistributor: dispatch failed %s: %s", task_id, dt.error)
        except Exception as e:
            dt.status = DistributedStatus.FAILED
            dt.error = f"Connection error: {e}"
            node.current_load = max(0, node.current_load - 1)
            node.healthy = False
            logger.error("RemoteDistributor: connection failed to %s: %s", node.node_id, e)

        return dt

    async def collect(self, task_id: str, timeout: float = 0) -> DistributedTask:
        import httpx

        dt = self._tasks.get(task_id)
        if not dt or dt.node_id not in self._nodes:
            return DistributedTask(task_id=task_id, status=DistributedStatus.FAILED, error="Not found")

        node = self._nodes[dt.node_id]
        wait_timeout = timeout or self._timeout

        try:
            url = f"{node.address.rstrip('/')}/api/v1/tasks/{task_id}"
            async with httpx.AsyncClient(timeout=wait_timeout) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    dt.result = data
                    status_str = data.get("status", "completed")
                    if status_str in ("completed", "done"):
                        dt.status = DistributedStatus.COMPLETED
                        node.current_load = max(0, node.current_load - 1)
                    elif status_str in ("failed", "error"):
                        dt.status = DistributedStatus.FAILED
                        dt.error = data.get("error_message", "Remote task failed")
                        node.current_load = max(0, node.current_load - 1)
                    else:
                        dt.status = DistributedStatus.RUNNING
                else:
                    dt.status = DistributedStatus.FAILED
                    dt.error = f"Status check returned {resp.status_code}"
        except Exception as e:
            dt.status = DistributedStatus.FAILED
            dt.error = f"Collection error: {e}"

        return dt

    async def status(self, task_id: str) -> DistributedTask | None:
        return self._tasks.get(task_id)

    async def list_nodes(self) -> list[NodeInfo]:
        return list(self._nodes.values())

    async def cancel(self, task_id: str) -> bool:
        import httpx

        dt = self._tasks.get(task_id)
        if not dt or dt.node_id not in self._nodes:
            return False

        node = self._nodes[dt.node_id]
        try:
            url = f"{node.address.rstrip('/')}/api/v1/tasks/{task_id}/cancel"
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url)
                if resp.status_code in (200, 204):
                    dt.status = DistributedStatus.FAILED
                    dt.error = "Cancelled by user"
                    node.current_load = max(0, node.current_load - 1)
                    logger.info("RemoteDistributor: cancelled %s on %s", task_id, node.node_id)
                    return True
        except Exception as e:
            logger.error("RemoteDistributor: cancel failed for %s: %s", task_id, e)

        return False
