from app.database import utcnow_iso
from app.insights import _percentile, overview, target_stats


def _seed(db, name, latencies, successes):
    tid = db.upsert_target(
        {
            "name": name,
            "url": "https://example.com",
            "method": "GET",
            "headers": "{}",
            "body": None,
            "expected_status": 200,
            "timeout": 10.0,
            "interval_seconds": 60,
            "enabled": 1,
        }
    )
    for ms, ok in zip(latencies, successes):
        db.insert_metric(
            {
                "target_id": tid,
                "ts": utcnow_iso(),
                "response_time_ms": ms,
                "status_code": 200 if ok else 500,
                "success": 1 if ok else 0,
                "error": None if ok else "boom",
                "response_size": 50,
            }
        )
    return tid


def test_percentile_interpolation():
    data = [10, 20, 30, 40, 50]
    assert _percentile(data, 50) == 30
    assert _percentile([], 95) is None
    assert _percentile([42], 99) == 42


def test_target_stats_computes_rates(db):
    tid = _seed(db, "svc", [100, 200, 300, 400], [True, True, True, False])
    stats = target_stats(db, tid, "24h")
    assert stats["samples"] == 4
    assert stats["errors"] == 1
    assert stats["error_rate"] == 25.0
    assert stats["uptime_pct"] == 75.0
    assert stats["min_ms"] == 100
    assert stats["max_ms"] == 400


def test_overview_flags_high_error_rate(db):
    _seed(db, "flaky", [100, 100, 100, 100], [False, False, False, True])
    result = overview(db, "24h")
    severities = {i["severity"] for i in result["insights"]}
    assert "critical" in severities


def test_overview_healthy_when_all_ok(db):
    _seed(db, "healthy", [50, 60, 55], [True, True, True])
    result = overview(db, "24h")
    assert result["insights"][0]["severity"] == "ok"
