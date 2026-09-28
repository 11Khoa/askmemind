import uuid

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_response_echoes_valid_request_id() -> None:
    response = client.get(
        "/does-not-exist",
        headers={"X-Request-ID": "request-123"},
    )

    assert response.status_code == 404
    assert response.headers["X-Request-ID"] == "request-123"


def test_response_replaces_invalid_request_id() -> None:
    response = client.get(
        "/does-not-exist",
        headers={"X-Request-ID": "invalid request id"},
    )

    assert response.status_code == 404
    assert uuid.UUID(response.headers["X-Request-ID"])
