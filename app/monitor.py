"""The probing engine: issues HTTP requests and records the outcome."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

import requests
from requests.exceptions import RequestException, Timeout

from .database import Database, utcnow_iso

logger = logging.getLogger(__name__)

# A single shared session enables connection pooling / keep-alive across probes.
_session = requests.Session()
_session.headers.update({"User-Agent": "api-performance-monitor/1.0"})


@dataclass
class ProbeResult:
    target_id: int
    ts: str
    response_time_ms: float | None
    status_code: int | None
    success: bool
    error: str | None
    response_size: int | None

    def as_metric(self) -> dict[str, Any]:
        return {
            "target_id": self.target_id,
            "ts": self.ts,
            "response_time_ms": self.response_time_ms,
            "status_code": self.status_code,
            "success": 1 if self.success else 0,
            "error": self.error,
            "response_size": self.response_size,
        }


def probe(target: dict[str, Any]) -> ProbeResult:
    """Issue a single request against ``target`` and measure the outcome."""
    ts = utcnow_iso()
    headers = {}
    try:
        headers = json.loads(target.get("headers") or "{}")
    except (TypeError, ValueError):
        logger.warning("Target %s has invalid headers JSON", target.get("name"))

    expected = int(target.get("expected_status", 200))
    method = (target.get("method") or "GET").upper()

    try:
        response = _session.request(
            method=method,
            url=target["url"],
            headers=headers or None,
            data=target.get("body"),
            timeout=float(target.get("timeout", 10)),
        )
        elapsed_ms = round(response.elapsed.total_seconds() * 1000, 2)
        size = len(response.content) if response.content is not None else 0
        success = response.status_code == expected
        error = None if success else f"unexpected status {response.status_code} (expected {expected})"
        return ProbeResult(
            target_id=target["id"],
            ts=ts,
            response_time_ms=elapsed_ms,
            status_code=response.status_code,
            success=success,
            error=error,
            response_size=size,
        )
    except Timeout:
        return ProbeResult(
            target_id=target["id"],
            ts=ts,
            response_time_ms=None,
            status_code=None,
            success=False,
            error=f"timeout after {target.get('timeout', 10)}s",
            response_size=None,
        )
    except RequestException as exc:
        return ProbeResult(
            target_id=target["id"],
            ts=ts,
            response_time_ms=None,
            status_code=None,
            success=False,
            error=f"{type(exc).__name__}: {exc}",
            response_size=None,
        )


def probe_and_store(db: Database, target: dict[str, Any]) -> ProbeResult:
    """Probe a target and persist the resulting metric sample."""
    result = probe(target)
    db.insert_metric(result.as_metric())
    level = logging.INFO if result.success else logging.WARNING
    logger.log(
        level,
        "probe %-24s status=%s time=%sms success=%s%s",
        target.get("name"),
        result.status_code,
        result.response_time_ms,
        result.success,
        f" error={result.error}" if result.error else "",
    )
    return result
