from unittest.mock import Mock

from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.database import get_db
from app.main import app


def test_liveness_does_not_require_database() -> None:
    response = TestClient(app).get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["X-Request-ID"]


def test_readiness_checks_database() -> None:
    db = Mock()
    app.dependency_overrides[get_db] = lambda: db

    try:
        response = TestClient(app).get("/health/ready")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
    db.execute.assert_called_once()


def test_readiness_returns_503_when_database_is_unavailable() -> None:
    db = Mock()
    db.execute.side_effect = OperationalError(
        statement="SELECT 1",
        params={},
        orig=RuntimeError("database unavailable"),
    )
    app.dependency_overrides[get_db] = lambda: db

    try:
        response = TestClient(app).get("/health/ready")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json() == {"detail": "Database is unavailable"}
