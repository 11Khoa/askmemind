import uuid
from pydantic import BaseModel, ConfigDict, Field
from app.models.demo_session import DemoSession
from app.services import demo_service
from app.services.audit_service import record_audit
from app.core.browser_auth import require_browser_csrf
from app.models.refresh_token import RefreshToken
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, HTTPException
from sqlalchemy.orm import Session, aliased
from starlette.concurrency import run_in_threadpool
from starlette.responses import StreamingResponse

from app.core.dependencies import get_db, require_admin
from app.models.user import User
from app.models.document import Document
from app.models.chunk import Chunk
from app.models.chat import Chat
from app.models.chat_message import ChatMessage
from app.models.audit_event import AuditEvent
from app.schemas.user import UserRead
from app.schemas.document import DocumentRead, SourcePassageRead
from app.schemas.chat import ChatRead, ChatMessageRead
from app.schemas.admin import Page, AdminUserCreate, AdminUserUpdate, AuditRead
from app.services import admin_service
from app.services.document_events import document_event_broker

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])
DB = Annotated[Session, Depends(get_db)]
Admin = Annotated[User, Depends(require_admin)]
PageNumber = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=100)]


class AdminDocumentRead(DocumentRead):
    owner_email: str


class AdminChatRead(ChatRead):
    owner_email: str


def paginate(query, page, page_size, serialize=lambda row: row):
    return {"items": [serialize(row) for row in query.offset((page - 1) * page_size).limit(page_size).all()],
            "total": query.order_by(None).count(), "page": page, "page_size": page_size}


@router.get("/documents/events")
async def document_events(request: Request, admin: Admin, db: DB):
    # require_admin authenticates before the stream opens; release its database
    # connection while idle. Bounded streams reauthorize on every reconnect.
    await run_in_threadpool(db.close)
    return StreamingResponse(
        document_event_broker.stream_admin(request), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


@router.get("/users", response_model=Page[UserRead])
def list_users(db: DB, page: PageNumber = 1, page_size: PageSize = 20,
               q: str = Query(default="", max_length=100)):
    query = db.query(User)
    if q:
        query = query.filter(User.email.icontains(q, autoescape=True))
    return paginate(query.order_by(User.created_at.desc(), User.id), page, page_size)


@router.post("/users", response_model=UserRead, status_code=201)
def create_user(payload: AdminUserCreate, request: Request, admin: Admin, db: DB):
    user = admin_service.create_user(db, admin.id, payload)
    request.state.audit_recorded = True
    return user


@router.patch("/users/{user_id}", response_model=UserRead)
def update_user(user_id: uuid.UUID, payload: AdminUserUpdate, request: Request, admin: Admin, db: DB):
    user = admin_service.update_user(db, admin.id, user_id, payload)
    request.state.audit_recorded = True
    return user


@router.get("/documents", response_model=Page[AdminDocumentRead])
def list_documents(db: DB, page: PageNumber = 1, page_size: PageSize = 20,
                   user_id: uuid.UUID | None = None, q: str = Query(default="", max_length=100)):
    query = db.query(Document, User.email).join(User, Document.user_id == User.id)
    if user_id:
        query = query.filter(Document.user_id == user_id)
    if q:
        query = query.filter(Document.original_filename.icontains(q, autoescape=True))
    return paginate(query.order_by(Document.created_at.desc(), Document.id), page, page_size,
        lambda row: {**DocumentRead.model_validate(row[0]).model_dump(), "owner_email": row[1]})


@router.get("/documents/{document_id}/chunks", response_model=Page[SourcePassageRead])
def document_chunks(document_id: uuid.UUID, db: DB, page: PageNumber = 1, page_size: PageSize = 20):
    if db.get(Document, document_id) is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return paginate(db.query(Chunk).filter(Chunk.document_id == document_id).order_by(Chunk.chunk_index), page, page_size)


@router.get("/chats", response_model=Page[AdminChatRead])
def list_chats(db: DB, page: PageNumber = 1, page_size: PageSize = 20,
               user_id: uuid.UUID | None = None, q: str = Query(default="", max_length=100)):
    query = db.query(Chat, User.email).join(User, Chat.user_id == User.id)
    if user_id:
        query = query.filter(Chat.user_id == user_id)
    if q:
        query = query.filter(Chat.title.icontains(q, autoescape=True))
    return paginate(query.order_by(Chat.updated_at.desc(), Chat.id), page, page_size,
        lambda row: {**ChatRead.model_validate(row[0]).model_dump(), "owner_email": row[1]})


@router.get("/chats/{chat_id}/messages", response_model=Page[ChatMessageRead])
def chat_messages(chat_id: uuid.UUID, db: DB, page: PageNumber = 1, page_size: PageSize = 20):
    if db.get(Chat, chat_id) is None:
        raise HTTPException(status_code=404, detail="Chat not found")
    return paginate(db.query(ChatMessage).filter(ChatMessage.chat_id == chat_id)
        .order_by(ChatMessage.message_index), page, page_size)


@router.get("/activity", response_model=Page[AuditRead])
def list_activity(db: DB, page: PageNumber = 1, page_size: PageSize = 20,
                  user_id: uuid.UUID | None = None, q: str = Query(default="", max_length=100)):
    actor, target = aliased(User), aliased(User)
    query = db.query(AuditEvent, actor.email, target.email).outerjoin(
        actor, actor.id == AuditEvent.actor_id,
    ).outerjoin(target, target.id == AuditEvent.target_user_id)
    if user_id:
        query = query.filter((AuditEvent.actor_id == user_id) | (AuditEvent.target_user_id == user_id))
    if q:
        query = query.filter(AuditEvent.action.icontains(q, autoescape=True))
    return paginate(query.order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc()), page, page_size,
        lambda row: {**AuditRead.model_validate(row[0]).model_dump(), "actor_email": row[1], "target_email": row[2]})


class DemoConfigUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    is_demo: bool
    demo_retention_minutes: int = Field(ge=15, le=1440)
    demo_upload_enabled: bool


@router.patch("/users/{user_id}/demo-config", response_model=UserRead,
              dependencies=[Depends(require_browser_csrf)])
def configure_demo(user_id: uuid.UUID, payload: DemoConfigUpdate, request: Request, admin: Admin, db: DB):
    admin_service.lock_admin(db, admin.id)
    user = db.query(User).filter(User.id == user_id).populate_existing().with_for_update().first()
    if user is None:
        raise HTTPException(404, "User not found")
    if payload.is_demo and user.role == "admin":
        raise HTTPException(409, "An administrator account cannot be a shared demo account")
    if user.is_demo and not payload.is_demo and db.query(DemoSession).filter(DemoSession.user_id == user.id).first():
        raise HTTPException(409, "Delete all demo data before disabling demo mode")
    before = {field: getattr(user, field) for field in type(payload).model_fields}
    if user.is_demo != payload.is_demo:
        user.token_version += 1
        db.query(RefreshToken).filter(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None)).update(
            {RefreshToken.revoked_at: datetime.now(UTC)}, synchronize_session=False)
    for field, value in payload.model_dump().items():
        setattr(user, field, value)
    record_audit(db, admin.id, "admin.demo.config.update", user.id, user.id,
                 details={"before": before, "after": payload.model_dump()})
    db.commit()
    request.state.audit_recorded = True
    return user


@router.delete("/users/{user_id}/demo-data", dependencies=[Depends(require_browser_csrf)])
def delete_demo_data(user_id: uuid.UUID, request: Request, admin: Admin, db: DB):
    admin_service.lock_admin(db, admin.id)
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "User not found")
    count = demo_service.cleanup_account(db, user.id, admin.id)
    request.state.audit_recorded = True
    return {"deleted": True, "sessions_deleted": count}


@router.get("/users/{user_id}/demo-sessions")
def list_demo_sessions(user_id: uuid.UUID, db: DB, page: PageNumber = 1, page_size: PageSize = 20):
    query = db.query(DemoSession).filter(DemoSession.user_id == user_id).order_by(DemoSession.created_at.desc())
    return paginate(query, page, page_size, lambda row: {
        "id": row.id, "created_at": row.created_at, "expires_at": row.expires_at,
        "notice_accepted_at": row.notice_accepted_at, "notice_version": row.notice_version,
    })


@router.delete("/users/{user_id}/demo-sessions/{session_id}", dependencies=[Depends(require_browser_csrf)])
def delete_one_demo_session(user_id: uuid.UUID, session_id: uuid.UUID, request: Request, admin: Admin, db: DB):
    admin_service.lock_admin(db, admin.id)
    session = db.query(DemoSession).filter(DemoSession.id == session_id, DemoSession.user_id == user_id).first()
    if session is None:
        raise HTTPException(404, "Demo session not found")
    demo_service.cleanup_session(db, session.id, actor_id=admin.id, action="admin.demo.session.delete")
    request.state.audit_recorded = True
    return {"deleted": True}
