"""Prometheus exposition endpoint.

Exposes the latest aggregated stats as Prometheus gauges so Grafana can also be
driven by a Prometheus datasource (in addition to reading SQLite directly).
"""

from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Gauge, generate_latest

from .database import Database
from .insights import target_stats


def render_prometheus(db: Database, window: str = "1h") -> tuple[bytes, str]:
    """Build a fresh registry from current stats and return the exposition text."""
    registry = CollectorRegistry()
    labels = ["target", "url"]

    up = Gauge("api_target_up", "1 if last check succeeded else 0", labels, registry=registry)
    avg = Gauge("api_response_time_avg_ms", "Average response time (ms)", labels, registry=registry)
    p95 = Gauge("api_response_time_p95_ms", "p95 response time (ms)", labels, registry=registry)
    p99 = Gauge("api_response_time_p99_ms", "p99 response time (ms)", labels, registry=registry)
    err = Gauge("api_error_rate_pct", "Error rate (%)", labels, registry=registry)
    uptime = Gauge("api_uptime_pct", "Uptime (%)", labels, registry=registry)
    samples = Gauge("api_samples_total", "Samples in window", labels, registry=registry)

    for target in db.list_targets(include_disabled=False):
        stats = target_stats(db, target["id"], window)
        lv = (target["name"], target["url"])
        last = stats.get("last_check") or {}
        up.labels(*lv).set(1 if last.get("success") else 0)
        if stats["avg_ms"] is not None:
            avg.labels(*lv).set(stats["avg_ms"])
        if stats["p95_ms"] is not None:
            p95.labels(*lv).set(stats["p95_ms"])
        if stats["p99_ms"] is not None:
            p99.labels(*lv).set(stats["p99_ms"])
        if stats["error_rate"] is not None:
            err.labels(*lv).set(stats["error_rate"])
        if stats["uptime_pct"] is not None:
            uptime.labels(*lv).set(stats["uptime_pct"])
        samples.labels(*lv).set(stats["samples"])

    return generate_latest(registry), CONTENT_TYPE_LATEST
