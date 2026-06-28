from app.database import utcnow_iso


def _target_row(name="svc"):
    return {
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


def test_upsert_is_idempotent_by_name(db):
    first = db.upsert_target(_target_row())
    second = db.upsert_target(_target_row())
    assert first == second
    assert len(db.list_targets()) == 1


def test_upsert_updates_existing(db):
    tid = db.upsert_target(_target_row())
    row = _target_row()
    row["url"] = "https://changed.example"
    db.upsert_target(row)
    assert db.get_target(tid)["url"] == "https://changed.example"


def test_delete_target_cascades_metrics(db):
    tid = db.upsert_target(_target_row())
    db.insert_metric(
        {
            "target_id": tid,
            "ts": utcnow_iso(),
            "response_time_ms": 12.3,
            "status_code": 200,
            "success": 1,
            "error": None,
            "response_size": 100,
        }
    )
    assert db.recent_metrics(tid)
    assert db.delete_target(tid) is True
    assert db.recent_metrics(tid) == []


def test_prune_removes_old_samples(db):
    tid = db.upsert_target(_target_row())
    db.insert_metric(
        {
            "target_id": tid,
            "ts": "2000-01-01T00:00:00.000000Z",
            "response_time_ms": 5,
            "status_code": 200,
            "success": 1,
            "error": None,
            "response_size": 10,
        }
    )
    assert db.prune(retention_days=30) == 1
    assert db.recent_metrics(tid) == []
