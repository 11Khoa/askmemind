import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.audit_event import AuditEvent
from app.models.user import User
from app.models.document import Document
from app.repositories.chat_repository import ChatRepository


@pytest.fixture
def admin_workspace(auth_client, db_session, tmp_path):
    credentials = {"email": "admin@example.com", "password": "password123"}
    assert auth_client.post("/auth/register", json=credentials).status_code == 201
    admin = db_session.query(User).filter_by(email=credentials["email"]).one()
    admin.role = "admin"
    db_session.commit()
    tokens = auth_client.post("/auth/token/login", json=credentials).json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    user_credentials = {"email": "client@example.com", "password": "password123"}
    response = auth_client.post("/auth/register", json=user_credentials)
    user_id = response.json()["id"]
    from uuid import UUID
    owner = db_session.get(User, UUID(user_id))
    user_tokens = auth_client.post("/auth/token/login", json=user_credentials).json()
    user_headers = {"Authorization": f"Bearer {user_tokens['access_token']}"}
    pdf = tmp_path / "private.pdf"
    pdf.write_bytes(b"%PDF-1.7\nprivate")
    document = Document(user_id=owner.id, filename="private.pdf", original_filename="private.pdf",
        file_path=str(pdf), content_type="application/pdf", file_size_bytes=pdf.stat().st_size,
        status="ready")
    db_session.add(document)
    db_session.commit()
    repository = ChatRepository(db_session)
    chat = repository.create_chat(owner.id, "Private research")
    repository.create_message(chat.id, 0, "user", "Private question")
    yield SimpleNamespace(client=auth_client, headers=headers, user_headers=user_headers,
        admin=admin, owner=owner, document=document, chat=chat, pdf=pdf)


def test_user_cannot_access_any_admin_surface(admin_workspace):
    w = admin_workspace
    for path in ("/admin/users", "/admin/documents", "/admin/chats", "/admin/activity",
                 f"/admin/chats/{w.chat.id}/messages", f"/admin/documents/{w.document.id}/chunks"):
        assert w.client.get(path, headers=w.user_headers).status_code == 403
    assert w.client.post("/admin/users", headers=w.user_headers, json={
        "email": "evil@example.com", "password": "password123", "role": "admin",
    }).status_code == 403
    assert w.client.patch(f"/admin/users/{w.owner.id}", headers=w.user_headers,
                         json={"role": "admin"}).status_code == 403


def test_admin_can_inspect_other_users_and_paginate(admin_workspace):
    w = admin_workspace
    page = w.client.get("/admin/users?page_size=1", headers=w.headers).json()
    assert page["total"] == 2 and len(page["items"]) == 1
    assert w.client.get("/admin/users?page_size=101", headers=w.headers).status_code == 422
    docs = w.client.get(f"/admin/documents?user_id={w.owner.id}", headers=w.headers).json()
    assert docs["items"][0]["owner_email"] == "client@example.com"
    assert w.client.get(f"/documents/{w.document.id}/file", headers=w.headers).content == w.pdf.read_bytes()
    messages = w.client.get(f"/admin/chats/{w.chat.id}/messages", headers=w.headers).json()
    assert messages["items"][0]["content"] == "Private question"
    assert w.client.get(f"/documents/{w.document.id}/file", headers=w.user_headers).status_code == 200


def test_admin_creates_selected_roles_and_audits_without_secrets(admin_workspace, db_session):
    w = admin_workspace
    for role in ("user", "admin"):
        response = w.client.post("/admin/users", headers=w.headers, json={
            "email": f"new-{role}@example.com", "password": "Never-log-this-password", "role": role,
        })
        assert response.status_code == 201
        assert response.json()["role"] == role
        assert "hashed_password" not in response.json()
    activity = w.client.get("/admin/activity?q=admin.user.create", headers=w.headers).json()
    assert activity["total"] == 2
    assert "Never-log" not in json.dumps(activity)
    assert all(event["actor_id"] == str(w.admin.id) for event in activity["items"])


@pytest.mark.parametrize("change", [{"role": "user"}, {"is_active": False}])
def test_last_active_admin_is_protected(admin_workspace, change):
    w = admin_workspace
    response = w.client.patch(f"/admin/users/{w.admin.id}", headers=w.headers, json=change)
    assert response.status_code == 409


def test_role_changes_and_account_locks_invalidate_existing_sessions(admin_workspace, db_session):
    w = admin_workspace
    response = w.client.patch(f"/admin/users/{w.owner.id}", headers=w.headers, json={"role": "admin"})
    assert response.status_code == 200
    assert w.client.get("/auth/me", headers=w.user_headers).status_code == 401
    fresh = w.client.post("/auth/token/login", json={"email": "client@example.com", "password": "password123"}).json()
    new_headers = {"Authorization": f"Bearer {fresh['access_token']}"}
    assert w.client.get("/admin/users", headers=new_headers).status_code == 200
    response = w.client.patch(f"/admin/users/{w.owner.id}", headers=w.headers, json={"is_active": False})
    assert response.status_code == 200
    assert w.client.get("/auth/me", headers=new_headers).status_code == 401
    assert w.client.post("/auth/token/refresh", json={"refresh_token": fresh["refresh_token"]}).status_code == 401


def test_admin_deletes_other_users_resources_with_transactional_audit(admin_workspace, db_session):
    w = admin_workspace
    owner_id, document_id, chat_id = w.owner.id, w.document.id, w.chat.id
    assert w.client.delete(f"/documents/{document_id}", headers=w.headers).status_code == 204
    assert not w.pdf.exists()
    assert w.client.delete(f"/chats/{chat_id}", headers=w.headers).status_code == 204
    events = db_session.query(AuditEvent).filter_by(target_user_id=owner_id).all()
    assert {event.action for event in events} == {"admin.document.delete", "admin.chat.delete"}
    assert all(event.actor_id == w.admin.id for event in events)


def test_request_auditing_records_login_outcomes_not_bodies(admin_workspace, monkeypatch):
    from app.services import audit_service
    w = admin_workspace
    events = []
    monkeypatch.setattr(audit_service, "write_request_audit", events.append)
    for password, expected in (("bad-password", 401), ("password123", 200)):
        assert w.client.post("/auth/token/login?secret=never-log", json={
            "email": "client@example.com", "password": password,
        }).status_code == expected
    assert [event["outcome"] for event in events] == ["failure", "success"]
    assert events[-1]["actor_id"] == w.owner.id
    assert all("secret" not in event["action"] for event in events)
    assert "password" not in json.dumps(events, default=str)
