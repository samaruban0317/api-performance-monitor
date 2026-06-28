# API Performance Monitor

[![CI](https://github.com/samaruban0317/api-performance-monitor/actions/workflows/ci.yml/badge.svg)](https://github.com/samaruban0317/api-performance-monitor/actions/workflows/ci.yml)

A system to **track and analyse API performance metrics** — response times, error
rates, and uptime — and turn them into actionable performance insights.

Built with **Python (Flask + Requests)**, **SQLite**, and **Grafana**.

---

## Features

- **Active probing engine** — periodically issues HTTP requests against configured
  endpoints using a pooled `requests` session and records latency, status code,
  payload size, and errors.
- **Per-target scheduling** — each endpoint is probed on its own interval via
  APScheduler; targets can be added/removed at runtime without a restart.
- **SQLite storage** — lightweight, file-based, WAL-mode persistence with indexed
  metric samples and automatic retention pruning.
- **Insights engine** — computes p50/p95/p99 latency percentiles, error rate,
  uptime %, and emits ranked, human-readable performance insights.
- **Built-in dashboard** — a zero-dependency live web UI (auto-refreshing) showing
  summary KPIs, insights, a sortable endpoint table, and per-endpoint latency charts.
- **Grafana-ready** — provisioned SQLite datasource + dashboard, plus a Prometheus
  `/metrics` endpoint for a Prometheus-driven setup.
- **REST API** — full CRUD over monitored targets and analytics queries.
- **Tested & containerised** — pytest suite and a one-command `docker compose up`.

---

## Architecture

```
                  ┌──────────────────────────────────────────────┐
                  │                Flask application               │
                  │                                                │
   config.yaml ──▶│  factory ─▶ targets synced into SQLite         │
                  │                                                │
                  │  APScheduler ──probe()──▶ requests ──▶ endpoints│
                  │       │                                        │
                  │       └─▶ metrics ─▶ SQLite (WAL)              │
                  │                          │                     │
   Browser  ◀─────│  /  dashboard            │                     │
   curl     ◀─────│  /api/* REST + insights ◀┤                     │
   Prometheus ◀───│  /metrics  exposition   ◀┘                     │
                  └──────────────────────────────────────────────┘
                                       │ reads .db
                                       ▼
                                   Grafana
```

| Module               | Responsibility                                          |
|----------------------|---------------------------------------------------------|
| `app/config.py`      | Env + YAML configuration, target specs                  |
| `app/database.py`    | SQLite schema and data-access layer                     |
| `app/monitor.py`     | The HTTP probing engine                                 |
| `app/scheduler.py`   | Per-target background scheduling + retention pruning     |
| `app/insights.py`    | Percentiles, error/uptime stats, insight generation     |
| `app/metrics.py`     | Prometheus exposition                                   |
| `app/api.py`         | REST API + dashboard routes                             |
| `app/factory.py`     | Application factory wiring it all together              |

---

## Quick start (local)

```bash
# 1. Install
python -m venv .venv
source .venv/Scripts/activate     # Windows (Git Bash);  use bin/activate on Linux/macOS
pip install -r requirements.txt

# 2. Configure (optional — sensible defaults exist)
cp .env.example .env

# 3. Run
python run.py
```

Open **http://localhost:5000** for the dashboard. The four sample endpoints in
`config.yaml` start being probed immediately.

### See it populated instantly (demo data)

```bash
python -m scripts.seed --hours 24      # generate 24h of synthetic history
python run.py
```

---

## Run with Grafana (Docker)

```bash
docker compose up --build
```

| Service   | URL                     | Notes                              |
|-----------|-------------------------|------------------------------------|
| Monitor   | http://localhost:5000   | Dashboard + API                    |
| Grafana   | http://localhost:3000   | login `admin` / `admin`            |

The **"API Performance Monitor"** dashboard is auto-provisioned in Grafana, backed
by the `frser-sqlite-datasource` plugin reading the same SQLite file the monitor
writes to.

---

## Configuration

Endpoints are defined in `config.yaml` and synced into the database on startup:

```yaml
defaults:
  method: GET
  expected_status: 200
  timeout: 10
  interval: 60

targets:
  - name: my-api
    url: https://api.example.com/health
    interval: 30
    expected_status: 200
```

Runtime behaviour is controlled by environment variables (see `.env.example`):
`DATABASE_PATH`, `CONFIG_PATH`, `ENABLE_SCHEDULER`, `RETENTION_DAYS`, `FLASK_PORT`, …

---

## REST API

| Method   | Path                              | Description                              |
|----------|-----------------------------------|------------------------------------------|
| `GET`    | `/`                               | Web dashboard                            |
| `GET`    | `/health`                         | Liveness probe                           |
| `GET`    | `/api/overview?window=1h\|24h\|7d`| Fleet summary, per-target stats, insights|
| `GET`    | `/api/targets`                    | List monitored targets                   |
| `POST`   | `/api/targets`                    | Create/update a target                   |
| `GET`    | `/api/targets/<id>?window=24h`    | Target details + stats + recent samples  |
| `DELETE` | `/api/targets/<id>`               | Remove a target                          |
| `POST`   | `/api/targets/<id>/check`         | Trigger an immediate probe               |
| `GET`    | `/metrics`                        | Prometheus exposition                    |

Example — add a target:

```bash
curl -X POST http://localhost:5000/api/targets \
  -H 'Content-Type: application/json' \
  -d '{"name":"my-api","url":"https://api.example.com/health","interval":30}'
```

---

## Testing

```bash
pytest
```

The suite covers the data layer, insights/percentile math, the probing engine
(mocked HTTP, success/error/timeout paths), and the REST API.

---

## Data model

```
targets(id, name, url, method, headers, body, expected_status,
        timeout, interval_seconds, enabled, created_at)

metrics(id, target_id → targets.id, ts, response_time_ms,
        status_code, success, error, response_size)
```

Indexes on `metrics(target_id, ts)` and `metrics(ts)` keep windowed aggregation fast.
Samples older than `RETENTION_DAYS` are pruned hourly.
