"""Fusion-Bench Python SDK — httpx client for REST API.

Importers/callers: external Python scripts, CI/CD integrations, fusion_bench/cicd/github_action.py.
Affected API: wraps all /api/v1/* endpoints; no new REST endpoints.
Data schema: mirrors API request/response pydantic models.
User instruction: "对比PRD、架构、计划文档，查看是否还存在遗留、defer的任务" (P2-08 SDK FEAT-029).
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class FusionBenchClient:
    def __init__(self, base_url: str = "http://localhost:11450", timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(base_url=self.base_url, timeout=timeout)

    # ── Tasks ──────────────────────────────────────────────────────────

    def create_task(
        self,
        model: str,
        executor_key: str = "speed",
        params: dict | None = None,
        level: str = "L1",
        timeout_seconds: int = 600,
    ) -> dict[str, Any]:
        resp = self._client.post(
            "/api/v1/tasks",
            json={
                "model": model,
                "executor_key": executor_key,
                "params": params or {},
                "level": level,
                "timeout_seconds": timeout_seconds,
            },
        )
        resp.raise_for_status()
        return resp.json()

    def list_tasks(
        self,
        page: int = 1,
        page_size: int = 20,
        status: str | None = None,
        model: str | None = None,
    ) -> list[dict]:
        resp = self._client.get(
            "/api/v1/tasks",
            params={
                "page": page,
                "page_size": page_size,
                "status": status,
                "model": model,
            },
        )
        resp.raise_for_status()
        return resp.json()

    def get_task(self, task_id: str) -> dict[str, Any]:
        resp = self._client.get(f"/api/v1/tasks/{task_id}")
        resp.raise_for_status()
        return resp.json()

    def cancel_task(self, task_id: str) -> dict[str, Any]:
        resp = self._client.post(f"/api/v1/tasks/{task_id}/cancel")
        resp.raise_for_status()
        return resp.json()

    def retry_task(self, task_id: str) -> dict[str, Any]:
        resp = self._client.post(f"/api/v1/tasks/{task_id}/retry")
        resp.raise_for_status()
        return resp.json()

    def get_task_logs(self, task_id: str, line_count: int = 50) -> dict[str, Any]:
        resp = self._client.get(f"/api/v1/tasks/{task_id}/logs", params={"line_count": line_count})
        resp.raise_for_status()
        return resp.json()

    # ── Suites ─────────────────────────────────────────────────────────

    def list_suites(self) -> list[dict]:
        resp = self._client.get("/api/v1/suites")
        resp.raise_for_status()
        return resp.json()

    def get_suite(self, suite_id: str) -> dict[str, Any]:
        resp = self._client.get(f"/api/v1/suites/{suite_id}")
        resp.raise_for_status()
        return resp.json()

    # ── Results ────────────────────────────────────────────────────────

    def get_result(self, task_id: str) -> dict[str, Any]:
        resp = self._client.get(f"/api/v1/results/{task_id}")
        resp.raise_for_status()
        return resp.json()

    def compare_results(self, task_ids: list[str]) -> dict[str, Any]:
        resp = self._client.post("/api/v1/results/compare", json={"task_ids": task_ids})
        resp.raise_for_status()
        return resp.json()

    def export_result(self, task_id: str, format: str = "json") -> Any:
        resp = self._client.post(f"/api/v1/results/{task_id}/export", json={"format": format})
        resp.raise_for_status()
        if format == "json":
            return resp.json()
        return resp.text

    def get_trend(
        self,
        model: str | None = None,
        executor_key: str | None = None,
        level: str | None = None,
    ) -> list[dict]:
        resp = self._client.get(
            "/api/v1/results/trend",
            params={
                "model": model,
                "executor_key": executor_key,
                "level": level,
            },
        )
        resp.raise_for_status()
        return resp.json()

    # ── Gates ──────────────────────────────────────────────────────────

    def check_gates(self, task_id: str, tier: str | None = None) -> dict[str, Any]:
        resp = self._client.post("/api/v1/gates/check", json={"task_id": task_id, "tier": tier})
        resp.raise_for_status()
        return resp.json()

    def list_gates(self, tier: str | None = None, level: str | None = None) -> list[dict]:
        resp = self._client.get("/api/v1/gates", params={"tier": tier, "level": level})
        resp.raise_for_status()
        return resp.json()

    # ── System ─────────────────────────────────────────────────────────

    def health(self) -> dict[str, Any]:
        resp = self._client.get("/api/v1/system/health")
        resp.raise_for_status()
        return resp.json()

    def resources(self) -> dict[str, Any]:
        resp = self._client.get("/api/v1/system/resources")
        resp.raise_for_status()
        return resp.json()

    def audit_logs(self, page: int = 1, page_size: int = 20) -> dict[str, Any]:
        resp = self._client.get("/api/v1/system/audit-logs", params={"page": page, "page_size": page_size})
        resp.raise_for_status()
        return resp.json()

    # ── Lifecycle ──────────────────────────────────────────────────────

    def close(self) -> None:
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
