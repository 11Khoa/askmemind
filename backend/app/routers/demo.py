from datetime import UTC, datetime
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User
from app.models.demo_session import DemoSession
from app.core.dependencies import get_current_user
from app.core.rate_limits import limit_login
from app.core.browser_auth import require_browser_csrf
from app.core.config import settings
from app.services import demo_service
from app.services.audit_service import record_audit
from pydantic import BaseModel, ConfigDict, Field


class NoticeAcceptance(BaseModel):
    model_config = ConfigDict(extra="forbid")
    notice_version: str = Field(min_length=1, max_length=64)

router = APIRouter(prefix="/demo", tags=["demo"])
DB = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


def require_demo(user):
    if not user.is_demo:
        raise HTTPException(403, "Demo account required")


@router.get("/status")
def status(request: Request, user: CurrentUser, db: DB):
    session = demo_service.current_session(db, user, request) if user.is_demo else None
    return demo_service.status(user, session)


@router.post("/bootstrap", dependencies=[Depends(require_browser_csrf), Depends(limit_login)])
def bootstrap(request: Request, response: Response, user: CurrentUser, db: DB):
    require_demo(user)
    try:
        session = demo_service.current_session(db, user, request)
    except HTTPException as error:
        if error.status_code != 410:
            raise
        session = demo_service.create_session(db, user)
    demo_service.set_cookie(response, session)
    return demo_service.status(user, session)


@router.post("/notice/accept", dependencies=[Depends(require_browser_csrf)])
def accept(payload: NoticeAcceptance, request: Request, user: CurrentUser, db: DB):
    require_demo(user)
    if payload.notice_version != settings.demo_notice_version:
        raise HTTPException(428, "Demo privacy notice changed. Review the current notice.")
    session = demo_service.current_session(db, user, request)
    session = db.scalar(select(DemoSession).where(DemoSession.id == session.id).with_for_update())
    if session is None or session.expires_at <= datetime.now(UTC):
        raise HTTPException(410, "Demo session expired")
    session.notice_version = settings.demo_notice_version
    session.notice_accepted_at = datetime.now(UTC)
    record_audit(db, user.id, "demo.notice.accept", target_user_id=user.id,
                 details={"notice_version": settings.demo_notice_version})
    db.commit()
    return demo_service.status(user, session)


@router.delete("/session", dependencies=[Depends(require_browser_csrf)])
def delete_current(request: Request, response: Response, user: CurrentUser, db: DB):
    require_demo(user)
    session = demo_service.current_session(db, user, request, allow_expired=True)
    demo_service.cleanup_session(db, session.id, actor_id=user.id, action="demo.session.self_delete")
    demo_service.clear_cookie(response)
    return {"deleted": True, "requires_bootstrap": True}
