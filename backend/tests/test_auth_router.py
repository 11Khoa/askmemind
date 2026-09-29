from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.dependencies import get_db
from app.main import app
from app.schemas.user import UserCreate, UserLogin


_PASSWORD = "password1122"


def test_register_then_login_with_different_email_case(db_session: Session) -> None:
    app.dependency_overrides[get_db] = lambda: db_session

    try:
        client = TestClient(app)

        register_response = client.post(
            "/auth/register",
            json={"email": "User@X.com", "password": _PASSWORD},
        )
        assert register_response.status_code == 201
        assert register_response.json()["email"] == "user@x.com"

        login_response = client.post(
            "/auth/login",
            json={"email": "user@x.com", "password": _PASSWORD},
        )
        assert login_response.status_code == 200
        assert login_response.json()["token_type"] == "bearer"
        assert login_response.json()["access_token"]
    finally:
        app.dependency_overrides.clear()


def test_register_same_email_with_different_case_returns_400(
    db_session: Session,
) -> None:
    app.dependency_overrides[get_db] = lambda: db_session

    try:
        client = TestClient(app)

        first_response = client.post(
            "/auth/register",
            json={"email": "CaseCheck@x.com", "password": _PASSWORD},
        )
        assert first_response.status_code == 201

        duplicate_response = client.post(
            "/auth/register",
            json={"email": "casecheck@x.com", "password": _PASSWORD},
        )
        assert duplicate_response.status_code == 400
        assert duplicate_response.json()["detail"] == "Email already registered"
    finally:
        app.dependency_overrides.clear()


def test_user_create_normalizes_email() -> None:
    payload = UserCreate(email=" User@X.com ", password=_PASSWORD)

    assert payload.email == "user@x.com"


def test_user_login_normalizes_email() -> None:
    payload = UserLogin(email=" User@X.com ", password=_PASSWORD)

    assert payload.email == "user@x.com"
