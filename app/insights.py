"""Performance analytics computed from stored metric samples.

All aggregation is pushed down into SQL so it stays fast even with large
sample volumes. Percentiles are computed in Python over the windowed rows,
which keeps the implementation portable across SQLite builds.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from .database import Database

# Named analysis windows -> number of seconds.
WINDOWS: dict[str, int] = {
    "1h": 3600,
    "24h": 86_400,
    "7d": 604_800,
}


def _percentile(sorted_values: list[float], pct: float) -> float | None:
    """Linear-interpolation percentile (NIST method) over a sorted list."""
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return round(sorted_values[0], 2)
    rank = (pct / 100) * (len(sorted_values) - 1)
    low = int(rank)
    high = min(low + 1, len(sorted_values) - 1)
    frac = rank - low
    value = sorted_values[low] + (sorted_values[high] - sorted_values[low]) * frac
    return round(value, 2)


def _window_cutoff(seconds: int) -> str:
    return (
        datetime.now(timezone.utc) - timedelta(seconds=seconds)
    ).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def target_stats(db: Database, target_id: int, window: str = "24h") -> dict[str, Any]:
    """Aggregate latency / error / uptime statistics for one target."""
    seconds = WINDOWS.get(window, WINDOWS["24h"])
    cutoff = _window_cutoff(seconds)

    with db.connect() as conn:
        summary = conn.execute(
            """
            SELECT
                COUNT(*)                                AS total,
                SUM(success)                            AS ok,
                AVG(response_time_ms)                   AS avg_ms,
                MIN(response_time_ms)                   AS min_ms,
                MAX(response_time_ms)                   AS max_ms,
                MAX(ts)                                 AS last_ts
            FROM metrics
            WHERE target_id = ? AND ts >= ?
            """,
            (target_id, cutoff),
        ).fetchone()

        latencies = [
            r["response_time_ms"]
            for r in conn.execute(
                """
                SELECT response_time_ms FROM metrics
                WHERE target_id = ? AND ts >= ? AND response_time_ms IS NOT NULL
                ORDER BY response_time_ms
                """,
                (target_id, cutoff),
            ).fetchall()
        ]

        last = conn.execute(
            """
            SELECT ts, status_code, success, response_time_ms, error
            FROM metrics WHERE target_id = ?
            ORDER BY ts DESC LIMIT 1
            """,
            (target_id,),
        ).fetchone()

    total = summary["total"] or 0
    ok = summary["ok"] or 0
    errors = total - ok

    return {
        "window": window,
        "samples": total,
        "errors": errors,
        "error_rate": round(errors / total * 100, 2) if total else None,
        "uptime_pct": round(ok / total * 100, 2) if total else None,
        "avg_ms": round(summary["avg_ms"], 2) if summary["avg_ms"] is not None else None,
        "min_ms": round(summary["min_ms"], 2) if summary["min_ms"] is not None else None,
        "max_ms": round(summary["max_ms"], 2) if summary["max_ms"] is not None else None,
        "p50_ms": _percentile(latencies, 50),
        "p95_ms": _percentile(latencies, 95),
        "p99_ms": _percentile(latencies, 99),
        "last_check": dict(last) if last else None,
    }


def overview(db: Database, window: str = "24h") -> dict[str, Any]:
    """Fleet-wide summary plus per-target stats and ranked insights."""
    targets = db.list_targets(include_disabled=True)
    per_target: list[dict[str, Any]] = []

    for target in targets:
        stats = target_stats(db, target["id"], window)
        per_target.append(
            {
                "id": target["id"],
                "name": target["name"],
                "url": target["url"],
                "enabled": bool(target["enabled"]),
                **stats,
            }
        )

    monitored = [t for t in per_target if t["samples"]]
    total_samples = sum(t["samples"] for t in monitored)
    total_errors = sum(t["errors"] for t in monitored)
    avg_values = [t["avg_ms"] for t in monitored if t["avg_ms"] is not None]

    return {
        "window": window,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "totals": {
            "targets": len(targets),
            "active": len(monitored),
            "samples": total_samples,
            "errors": total_errors,
            "global_error_rate": round(total_errors / total_samples * 100, 2)
            if total_samples
            else None,
            "global_avg_ms": round(sum(avg_values) / len(avg_values), 2)
            if avg_values
            else None,
        },
        "targets": per_target,
        "insights": _generate_insights(per_target),
    }


def _generate_insights(per_target: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Heuristic, human-readable performance insights."""
    insights: list[dict[str, str]] = []

    for t in per_target:
        if not t["samples"]:
            continue
        name = t["name"]

        if t["error_rate"] is not None and t["error_rate"] >= 10:
            insights.append(
                {
                    "severity": "critical",
                    "target": name,
                    "message": f"{name} has a {t['error_rate']}% error rate "
                    f"over the last {t['window']}.",
                }
            )

        if t["p95_ms"] is not None and t["p95_ms"] >= 1000:
            insights.append(
                {
                    "severity": "warning",
                    "target": name,
                    "message": f"{name} p95 latency is {t['p95_ms']}ms — "
                    "responses are slow under load.",
                }
            )

        if (
            t["p99_ms"] is not None
            and t["avg_ms"] is not None
            and t["avg_ms"] > 0
            and t["p99_ms"] >= t["avg_ms"] * 4
        ):
            insights.append(
                {
                    "severity": "info",
                    "target": name,
                    "message": f"{name} shows high latency variance "
                    f"(p99 {t['p99_ms']}ms vs avg {t['avg_ms']}ms).",
                }
            )

    if not insights:
        insights.append(
            {
                "severity": "ok",
                "target": "*",
                "message": "All monitored endpoints are healthy and responsive.",
            }
        )

    severity_order = {"critical": 0, "warning": 1, "info": 2, "ok": 3}
    insights.sort(key=lambda i: severity_order.get(i["severity"], 9))
    return insights
