import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, HTTPException
from sqlalchemy.orm import Session

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
    query = db.query(AuditEvent)
    if user_id:
        query = query.filter((AuditEvent.actor_id == user_id) | (AuditEvent.target_user_id == user_id))
    if q:
        query = query.filter(AuditEvent.action.icontains(q, autoescape=True))
    return paginate(query.order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc()), page, page_size)
