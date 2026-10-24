"""Audit metadata only: never collect bodies, tokens, passwords or query strings."""
import logging
import uuid

from starlette.concurrency import run_in_threadpool

from app.core.logging import get_request_id
from app.database import SessionLocal
from app.models.audit_event import AuditEvent

logger = logging.getLogger(__name__)


def record_audit(db, actor_id, action, resource_id=None, target_user_id=None, details=None):
    db.add(AuditEvent(
        actor_id=actor_id, action=action, resource_id=resource_id,
        target_user_id=target_user_id, outcome="success",
        request_id=get_request_id(), details=details,
    ))


def write_request_audit(event):
    with SessionLocal() as db:
        db.add(AuditEvent(**event))
        db.commit()


class AuditMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        status = 500
        request_id = None

        async def audited_send(message):
            nonlocal status, request_id
            if message["type"] == "http.response.start":
                status = message["status"]
                request_id = dict(message.get("headers", [])).get(b"x-request-id", b"").decode()
            await send(message)

        try:
            await self.app(scope, receive, audited_send)
        finally:
            await self.observe(scope, status, request_id)

    async def observe(self, scope, status, request_id):
        route = scope.get("route")
        pattern = getattr(route, "path", "")
        state = scope.get("state", {})
        if not pattern.startswith(("/auth/", "/documents", "/chats", "/admin/")):
            return
        if pattern in ("/auth/me", "/documents/events") or state.get("audit_recorded"):
            return
        params = scope.get("path_params", {})
        resource_id = next((value for key, value in params.items() if key.endswith("_id")), None)
        event = {
            "actor_id": state.get("actor_id"), "target_user_id": state.get("target_user_id"),
            "action": f"{scope['method']} {pattern}",
            "resource_id": resource_id if isinstance(resource_id, uuid.UUID) else None,
            "outcome": state.get("audit_outcome", "success" if status < 400 else "failure"),
            "request_id": request_id or None, "details": {"status_code": status},
        }
        try:
            await run_in_threadpool(write_request_audit, event)
        except Exception:
            # Privileged mutations record transactionally; ordinary request
            # observation must not turn a completed operation into a retry.
            logger.exception("audit.request.write_failed")
