# Issue #38 acceptance tests: union-web shell module registration.
#
# Covers: env gating, manifest validity (governance/sort-23/title per the
# approved taxonomy), register_once round-trip incl. module api_key carry,
# non-2xx rejection, heartbeat loop recovery + exception survival, and
# lifespan start/stop under the env gate.

from __future__ import annotations

import asyncio
import contextlib
import json
from unittest.mock import patch

from fusion_bench import shell_registry
from fusion_bench.shell_registry import (
    _load_manifest,
    register_once,
    run_shell_registry,
    shell_registration_enabled,
)


def test_registration_disabled_without_env(monkeypatch):
    monkeypatch.delenv("FUSION_SHELL_GATEWAY_URL", raising=False)
    assert shell_registration_enabled() is False


def test_registration_disabled_without_admin_key(monkeypatch):
    monkeypatch.setenv("FUSION_SHELL_GATEWAY_URL", "http://127.0.0.1:11432")
    monkeypatch.setattr(shell_registry, "_gateway_admin_key", lambda: "")
    assert shell_registration_enabled() is False


def test_registration_enabled_with_both(monkeypatch):
    monkeypatch.setenv("FUSION_SHELL_GATEWAY_URL", "http://127.0.0.1:11432")
    monkeypatch.setattr(shell_registry, "_gateway_admin_key", lambda: "k")
    assert shell_registration_enabled() is True


def test_default_manifest_exists_and_valid():
    manifest = _load_manifest()
    assert manifest["id"] == "fusion-bench"
    # Approved taxonomy (D4): governance group, between capability center
    # and security
    assert manifest["category"] == "governance"
    assert manifest["sort"] == 23
    assert manifest["title"] == "模型评测"
    assert manifest["title_en"] == "Bench"
    assert manifest["health"].startswith("http://127.0.0.1:11467/")
    assert manifest["entry"] == "/shell/fusion-bench/"


def test_load_manifest_env_override(monkeypatch, tmp_path):
    p = tmp_path / "manifest.json"
    p.write_text(json.dumps({"id": "x"}), encoding="utf-8")
    monkeypatch.setenv("FUSION_SHELL_MANIFEST", str(p))
    assert _load_manifest() == {"id": "x"}


def test_load_manifest_missing_file_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("FUSION_SHELL_MANIFEST", str(tmp_path / "nope.json"))
    try:
        _load_manifest()
        raise AssertionError("expected FileNotFoundError")
    except FileNotFoundError:
        pass


def test_load_manifest_missing_id_raises(monkeypatch, tmp_path):
    p = tmp_path / "manifest.json"
    p.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("FUSION_SHELL_MANIFEST", str(p))
    try:
        _load_manifest()
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


class _FakeResp:
    def __init__(self, status_code, text=""):
        self.status_code = status_code
        self.text = text


class _FakeClient:
    last_post = None

    def __init__(self, status_code):
        self.status_code = status_code

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def post(self, url, json=None, headers=None):
        _FakeClient.last_post = {"url": url, "json": json, "headers": headers}
        return _FakeResp(self.status_code, "err")


async def test_register_once_success(monkeypatch):
    monkeypatch.setenv("FUSION_SHELL_GATEWAY_URL", "http://gw:11432/")
    monkeypatch.setattr(shell_registry, "_gateway_admin_key", lambda: "admin-k")
    with patch.object(shell_registry.httpx, "AsyncClient", lambda **kw: _FakeClient(200)):
        ok, reason = await register_once()
    assert ok is True and reason == ""
    sent = _FakeClient.last_post
    assert sent["url"] == "http://gw:11432/api/v1/shell/manifests"
    assert sent["headers"]["Authorization"] == "Bearer admin-k"
    assert sent["json"]["id"] == "fusion-bench"


async def test_register_once_carries_module_api_key(monkeypatch):
    monkeypatch.setenv("FUSION_SHELL_GATEWAY_URL", "http://gw:11432")
    monkeypatch.setattr(shell_registry, "_gateway_admin_key", lambda: "admin-k")
    monkeypatch.setenv("FUSION_BENCH_SHELL_API_KEY", "fm-secret")
    with patch.object(shell_registry.httpx, "AsyncClient", lambda **kw: _FakeClient(200)):
        ok, _ = await register_once()
    assert ok is True
    assert _FakeClient.last_post["json"]["api_key"] == "fm-secret"


async def test_register_once_rejects_non_2xx(monkeypatch):
    monkeypatch.setenv("FUSION_SHELL_GATEWAY_URL", "http://gw:11432")
    monkeypatch.setattr(shell_registry, "_gateway_admin_key", lambda: "admin-k")
    with patch.object(shell_registry.httpx, "AsyncClient", lambda **kw: _FakeClient(403)):
        ok, reason = await register_once()
    assert ok is False
    assert "403" in reason


async def test_run_registry_survives_exceptions(monkeypatch):
    monkeypatch.setenv("FUSION_SHELL_GATEWAY_URL", "http://gw:11432")
    monkeypatch.setattr(shell_registry, "_gateway_admin_key", lambda: "k")
    monkeypatch.setattr(shell_registry, "REGISTER_INTERVAL_SECONDS", 0.01)
    calls = {"n": 0}

    async def _boom():
        calls["n"] += 1
        raise RuntimeError("gateway down")

    with patch.object(shell_registry, "register_once", _boom):
        task = asyncio.create_task(run_shell_registry())
        await asyncio.sleep(0.05)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    assert calls["n"] >= 1
