"""CI/CD webhook notification - gate block webhook for pipeline integration.

Importers/callers: orchestrator/gate_engine.py calls notify_webhook() on gate block.
Affected API: no new REST endpoints; outbound HTTP POST to configured webhook_url.
Data schema: WebhookConfig (url, secret, events, enabled, timeout_seconds); WebhookPayload (event, suite_id, model, gate_name, gate_passed, metric_value, threshold, timestamp, detail).
User instruction: "把所有没完全做完，没启动做，有差距的全部启动补齐" (Enhancement B gate block webhook).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger(__name__)


@dataclass
class WebhookConfig:
    url: str
    secret: str = ""
    events: list[str] = field(default_factory=lambda: ["gate_blocked", "gate_passed", "suite_completed"])
    enabled: bool = True
    timeout_seconds: int = 10


@dataclass
class WebhookPayload:
    event: str
    suite_id: str = ""
    model: str = ""
    gate_name: str = ""
    gate_passed: bool = False
    metric_value: float = 0.0
    threshold: float = 0.0
    timestamp: str = ""
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event": self.event,
            "suite_id": self.suite_id,
            "model": self.model,
            "gate_name": self.gate_name,
            "gate_passed": self.gate_passed,
            "metric_value": self.metric_value,
            "threshold": self.threshold,
            "timestamp": self.timestamp or time.strftime("%Y-%m-%dT%H:%M:%S"),
            "detail": self.detail,
        }


def _sign_payload(payload_json: str, secret: str) -> str:
    if not secret:
        return ""
    return hmac.new(secret.encode(), payload_json.encode(), hashlib.sha256).hexdigest()


async def notify_webhook(config: WebhookConfig, payload: WebhookPayload) -> bool:
    if not config.enabled or not config.url:
        return False

    if payload.event not in config.events:
        return False

    data = payload.to_dict()
    body = json.dumps(data, ensure_ascii=False)
    headers = {"Content-Type": "application/json"}
    sig = _sign_payload(body, config.secret)
    if sig:
        headers["X-Webhook-Signature"] = sig

    try:
        async with httpx.AsyncClient(timeout=config.timeout_seconds) as client:
            resp = await client.post(config.url, content=body, headers=headers)
            if resp.status_code < 400:
                logger.info(
                    "Webhook %s sent: %s -> %d",
                    payload.event,
                    config.url,
                    resp.status_code,
                )
                return True
            logger.warning(
                "Webhook %s failed: %d %s",
                payload.event,
                resp.status_code,
                resp.text[:200],
            )
            return False
    except Exception as e:
        logger.error("Webhook notification error: %s", e)
        return False
