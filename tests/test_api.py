def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"


def test_dashboard_renders(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"API Performance Monitor" in resp.data


def test_create_and_list_target(client):
    resp = client.post(
        "/api/targets",
        json={"name": "demo", "url": "https://example.com", "interval": 30},
    )
    assert resp.status_code == 201
    created = resp.get_json()
    assert created["name"] == "demo"
    assert created["interval_seconds"] == 30

    listing = client.get("/api/targets").get_json()
    assert any(t["name"] == "demo" for t in listing)


def test_create_target_requires_fields(client):
    resp = client.post("/api/targets", json={"name": "no-url"})
    assert resp.status_code == 400


def test_delete_target(client):
    created = client.post(
        "/api/targets", json={"name": "tmp", "url": "https://example.com"}
    ).get_json()
    resp = client.delete(f"/api/targets/{created['id']}")
    assert resp.status_code == 200
    assert client.get(f"/api/targets/{created['id']}").status_code == 404


def test_overview_window_validation(client):
    assert client.get("/api/overview?window=bad").status_code == 400
    assert client.get("/api/overview?window=24h").status_code == 200


def test_prometheus_metrics_endpoint(client):
    client.post("/api/targets", json={"name": "p", "url": "https://example.com"})
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert b"api_target_up" in resp.data
