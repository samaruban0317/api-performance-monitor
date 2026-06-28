"""Populate the database with synthetic metrics for demos / screenshots.

Useful when you want to see the dashboard and Grafana panels populated without
waiting for live probes to accumulate history.

Usage:
    python -m scripts.seed --hours 24
"""

from __future__ import annotations

import argparse
import random
from datetime import datetime, timedelta, timezone

from app.config import settings
from app.database import Database

DEMO_TARGETS = [
    # name, url, base latency (ms), jitter, error probability
    ("payments-api", "https://api.example.com/payments", 80, 40, 0.01),
    ("search-api", "https://api.example.com/search", 220, 120, 0.03),
    ("auth-api", "https://api.example.com/auth", 60, 20, 0.005),
    ("recommendations-api", "https://api.example.com/recommend", 450, 300, 0.08),
]


def seed(hours: int) -> None:
    db = Database(settings.db_file)
    db.init_db()

    now = datetime.now(timezone.utc)
    total = 0

    for name, url, base, jitter, err_p in DEMO_TARGETS:
        tid = db.upsert_target(
            {
                "name": name,
                "url": url,
                "method": "GET",
                "headers": "{}",
                "body": None,
                "expected_status": 200,
                "timeout": 10.0,
                "interval_seconds": 60,
                "enabled": 1,
            }
        )
        ts = now - timedelta(hours=hours)
        while ts < now:
            failed = random.random() < err_p
            latency = None if failed else max(1, random.gauss(base, jitter))
            db.insert_metric(
                {
                    "target_id": tid,
                    "ts": ts.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                    "response_time_ms": round(latency, 2) if latency else None,
                    "status_code": 500 if failed else 200,
                    "success": 0 if failed else 1,
                    "error": "simulated 500" if failed else None,
                    "response_size": 0 if failed else random.randint(200, 4000),
                }
            )
            total += 1
            ts += timedelta(minutes=1)

    print(f"Seeded {total} samples across {len(DEMO_TARGETS)} targets into {settings.db_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed synthetic monitoring data.")
    parser.add_argument("--hours", type=int, default=24, help="hours of history to generate")
    args = parser.parse_args()
    seed(args.hours)
