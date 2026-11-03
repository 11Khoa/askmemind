"""Browser demo lifecycle and the shared, retryable cleanup implementation."""
import logging
import hashlib
import hmac
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from fastapi import HTTPException
from sqlalchemy import select, func, delete, update
from app.core.config import settings
from app.models.demo_session import DemoSession
from app.models.user import User
from app.models.document import Document
from app.models.chat import Chat
from app.models.refresh_token import RefreshToken
from app.services.audit_service import record_audit

logger = logging.getLogger(__name__)
COOKIE = "askmemind_demo"


def cookie_signature(identifier):
    # Domain-separated signature: a known database UUID is not a cookie credential.
    return hmac.new(settings.secret_key.encode(), f"demo-session:{identifier}".encode(), hashlib.sha256).hexdigest()


def set_cookie(response, session):
    response.set_cookie(COOKIE, f"{session.id}.{cookie_signature(session.id)}", httponly=True,
        secure=settings.auth_refresh_cookie_secure,
        samesite=settings.auth_refresh_cookie_samesite, path="/",
        max_age=max(0, int((session.expires_at - datetime.now(UTC)).total_seconds())))


def clear_cookie(response):
    response.delete_cookie(COOKIE, path="/", httponly=True,
        secure=settings.auth_refresh_cookie_secure, samesite=settings.auth_refresh_cookie_samesite)


def current_session(db, user, request, *, allow_expired=False):
    try:
        raw_id, signature = request.cookies.get(COOKIE, "").split(".", 1)
        identifier = uuid.UUID(raw_id)
        if not hmac.compare_digest(signature, cookie_signature(identifier)):
            raise ValueError("Invalid session signature")
    except (ValueError, TypeError):
        raise HTTPException(410, "Demo session missing or expired. Start a new demo session.") from None
    statement = select(DemoSession).where(DemoSession.id == identifier, DemoSession.user_id == user.id)
    if not allow_expired:
        statement = statement.where(DemoSession.expires_at > func.clock_timestamp())
    session = db.scalar(statement.execution_options(populate_existing=True))
    if session is None:
        raise HTTPException(410, "Demo session missing or expired. Start a new demo session.")
    return session


def create_session(db, user):
    # Serialize creation with admin configuration and bound disposable sessions.
    account = db.scalar(select(User).where(User.id == user.id).with_for_update().execution_options(populate_existing=True))
    if not account.is_demo:
        raise HTTPException(409, "Account is no longer a demo account. Sign in again.")
    if db.scalar(select(func.count()).select_from(DemoSession).where(DemoSession.user_id == user.id)) >= settings.demo_max_sessions_per_account:
        raise HTTPException(429, "Demo account session limit reached. Try again after cleanup.")
    now = datetime.now(UTC)
    session = DemoSession(user_id=user.id, created_at=now,
                          expires_at=now + timedelta(minutes=account.demo_retention_minutes))
    db.add(session)
    record_audit(db, user.id, "demo.session.create", target_user_id=user.id)
    db.commit()
    db.refresh(session)
    return session


def status(user, session=None):
    return {"is_demo": user.is_demo, "retention_minutes": int((session.expires_at - session.created_at).total_seconds() / 60) if session else user.demo_retention_minutes,
            "upload_enabled": user.demo_upload_enabled, "notice_version": settings.demo_notice_version,
            "notice_accepted": bool(session and session.notice_accepted_at and session.notice_version == settings.demo_notice_version),
            "expires_at": session.expires_at if session else None}


def cleanup_session(db, identifier, *, actor_id=None, action="demo.session.expire"):
    """Revoke first, then remove files and cascaded rows. File failures remain retryable.

    Session row always precedes aggregate row locks. Workers never retain this
    lock during OCR/network calls. No advisory processing lock is needed here.
    """
    session = db.scalar(select(DemoSession).where(DemoSession.id == identifier).with_for_update())
    if session is None:
        return False
    owner = session.user_id
    session.expires_at = datetime.now(UTC)
    db.execute(update(Document).where(Document.demo_session_id == identifier).values(
        status="deleting", processing_attempt_id=None))
    db.commit()
    session = db.scalar(select(DemoSession).where(DemoSession.id == identifier).with_for_update())
    if session is None:
        return False
    try:
        paths = db.scalars(select(Document.file_path).where(Document.demo_session_id == identifier)).all()
        for path in paths:
            Path(path).unlink(missing_ok=True)
        # Explicit deletes also cover installations without ORM relationship loading.
        db.execute(delete(Chat).where(Chat.demo_session_id == identifier))
        db.execute(delete(Document).where(Document.demo_session_id == identifier))
        db.delete(session)
        record_audit(db, actor_id, action, target_user_id=owner, details={"documents_deleted": len(paths)})
        db.commit()
        logger.info("demo.cleanup.completed", extra={"event_data": {"documents_deleted": len(paths)}})
        return True
    except OSError:
        db.rollback()
        logger.warning("demo.cleanup.file_failed")
        raise HTTPException(503, "Demo cleanup incomplete. Please retry.") from None


def cleanup_account(db, user_id, actor_id):
    identifiers = db.scalars(select(DemoSession.id).where(DemoSession.user_id == user_id)).all()
    for identifier in identifiers:
        cleanup_session(db, identifier, actor_id=actor_id, action="admin.demo.data.delete")
    record_audit(db, actor_id, "admin.demo.account_data.delete", target_user_id=user_id,
                 details={"sessions_deleted": len(identifiers)})
    db.commit()
    return len(identifiers)
