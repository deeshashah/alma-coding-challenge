def test_health_returns_ok(client):
    """GET /api/health responds 200 with {"status": "ok"}."""
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
