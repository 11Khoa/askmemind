import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.core.dependencies import require_admin


def test_only_admin_passes_permission_check():
    admin = SimpleNamespace(role="admin")
    assert require_admin(admin) is admin
    for user in (SimpleNamespace(role="user"), SimpleNamespace()):
        with pytest.raises(HTTPException) as error:
            require_admin(user)
        assert error.value.status_code == 403


def test_public_registration_cannot_choose_role(auth_client):
    response = auth_client.post("/auth/register", json={
        "email": "injected@example.com", "password": "password123", "role": "admin",
    })
    assert response.status_code == 422
    response = auth_client.post("/auth/register", json={
        "email": "ordinary@example.com", "password": "password123",
    })
    assert response.status_code == 201
    assert response.json()["role"] == "user"


def test_user_cannot_call_delete_endpoints(auth_client, auth_tokens):
    headers = {"Authorization": f"Bearer {auth_tokens['access_token']}"}
    for path in (f"/documents/{uuid.uuid4()}", f"/chats/{uuid.uuid4()}"):
        response = auth_client.delete(path, headers=headers)
        assert response.status_code == 403
