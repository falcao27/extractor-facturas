def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok", "llm_provider": "anthropic"}
    assert response.headers["x-request-id"]
