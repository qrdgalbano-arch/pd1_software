from fastapi.testclient import TestClient

from app.main import app


def test_trusted_host_middleware_rejects_unknown_host():
    with TestClient(app, base_url="http://untrusted.example") as client:
        response = client.get("/health")

    assert response.status_code == 400
    assert response.text == "Invalid host header"
