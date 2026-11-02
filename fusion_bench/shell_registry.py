# Union-web shell module self-registration + heartbeat (#38, PRD §5.2).
# On startup, register web/manifest.json into the fusion-gateway shell
# registry (POST /api/v1/shell/manifests, Bearer admin key), then heartbeat
# at a fixed interval — modules missing heartbeats show unreachable (gray
# dot) in the shell menu instead of being removed (MT-D).
#
# Env switches — both required to enable:
# - FUSION_SHELL_GATEWAY_URL: gateway base URL, e.g. http://127.0.0.1:11432
# - gateway admin key via fusion_core.config.admin_key() (canonical
#   FUSION_ADMIN_KEY; prod-missing RuntimeError converges in fusion-core)
#
# Optional:
# - FUSION_SHELL_MANIFEST: manifest path override (default web/manifest.json)
# - FUSION_BENCH_SHELL_API_KEY: module api_key carried in the registration
#   body (manifest.json api_key_env). When absent the gateway issues an fm-
#   service key; without a module key the proxied upstream calls 401, so
#   self-registration should stay off in that setup.
#
# The /shell/fusion-bench/ reverse proxy itself is gateway-side config
# (static web_shell.modules); the dynamic manifest drives menu/entry only.

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

GATEWAY_URL_ENV = "FUSION_SHELL_GATEWAY_URL"
ADMIN_KEY_ENV = "FUSION_ADMIN_KEY"
MANIFEST_PATH_ENV = "FUSION_SHELL_MANIFEST"
MODULE_KEY_ENV = "FUSION_BENCH_SHELL_API_KEY"
REGISTER_INTERVAL_SECONDS = 15.0
HTTP_TIMEOUT_SECONDS = 5.0
# One heartbeat per interval; a down gateway must not spam one warning per
# tick — rate-limit failure logs.
FAILURE_LOG_INTERVAL_SECONDS = 300.0


def _default_manifest_path() -> Path:
    return Path(__file__).resolve().parent.parent / "web" / "manifest.json"


def _gateway_admin_key() -> str:
    # Single-point resolution via fusion_core.config.admin_key (issue #35
    # convention). Bare installs without fusion-core fall back to the
    # canonical env name only — no alias chain duplicated here (pattern:
    # fusion-security #57).
    try:
        from fusion_core.config import admin_key

        return admin_key()
    except ImportError:
        key = os.environ.get(ADMIN_KEY_ENV, "")
        if not key:
            logger.warning(
                f"{ADMIN_KEY_ENV} unset: shell gateway registration unavailable (request from fusion-gateway admin API)"
            )
        return key


def shell_registration_enabled() -> bool:
    # Short-circuit on URL; admin-key resolution (and the prod-missing
    # RuntimeError) only fires when registration is actually wanted.
    if not os.environ.get(GATEWAY_URL_ENV, "").strip():
        return False
    return bool(_gateway_admin_key().strip())


def _load_manifest() -> dict[str, Any]:
    path = Path(os.environ.get(MANIFEST_PATH_ENV, "").strip() or _default_manifest_path())
    if not path.exists():
        raise FileNotFoundError(f"shell manifest not found: {path}")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if not manifest.get("id"):
        raise ValueError(f"shell manifest missing id: {path}")
    return manifest


async def register_once() -> tuple[bool, str]:
    # Single register/heartbeat round-trip; gateway accepts (True, ""),
    # otherwise (False, reason). FUSION_BENCH_SHELL_API_KEY set -> body
    # carries api_key (gateway proxy prefers it for upstream injection);
    # key never logged.
    gateway = os.environ.get(GATEWAY_URL_ENV, "").strip().rstrip("/")
    gw_key = _gateway_admin_key().strip()
    manifest = _load_manifest()
    body: dict[str, Any] = dict(manifest)
    module_key = os.environ.get(MODULE_KEY_ENV, "").strip()
    if module_key:
        body["api_key"] = module_key
    url = f"{gateway}/api/v1/shell/manifests"
    headers = {"Authorization": f"Bearer {gw_key}"}
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
        resp = await client.post(url, json=body, headers=headers)
    if resp.status_code in (200, 201, 204):
        return True, ""
    return False, f"registration failed {url} -> {resp.status_code} {resp.text[:200]}"


async def run_shell_registry() -> None:
    # Long-lived lifespan task: register + heartbeat until cancelled. Never
    # raises — a dead gateway must not take down the bench service; every
    # failure logs and retries on the next interval.
    logger.info(
        "shell registry: enabled gateway=%s manifest=%s",
        os.environ.get(GATEWAY_URL_ENV, ""),
        os.environ.get(MANIFEST_PATH_ENV, "") or _default_manifest_path(),
    )
    last_failure_log = 0.0
    consecutive_failures = 0
    while True:
        exc: Exception | None = None
        try:
            ok, reason = await register_once()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            ok = False
            exc = e
            reason = f"round-trip failed: {type(e).__name__}: {e}"
        if ok:
            if consecutive_failures:
                logger.info("shell registry: recovered after %d failures", consecutive_failures)
            consecutive_failures = 0
        else:
            consecutive_failures += 1
            now = time.monotonic()
            if now - last_failure_log >= FAILURE_LOG_INTERVAL_SECONDS:
                last_failure_log = now
                logger.warning("shell registry: %s", reason, exc_info=exc is not None)
        await asyncio.sleep(REGISTER_INTERVAL_SECONDS)
