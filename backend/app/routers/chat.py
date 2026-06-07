import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.dependencies import get_chat_service
from app.schemas.chat import (
    ChatCreate,
    ChatMessageCreate,
    ChatMessageRead,
    ChatRead,
)
from app.services.chat_service import ChatService

router = APIRouter(
    prefix="/chats",
    tags=["chats"],
)


@router.get("", response_model=list[ChatRead])
def list_chats(
    user_id: uuid.UUID,
    chat_service: Annotated[ChatService, Depends(get_chat_service)],
):
    return chat_service.list_user_chats(user_id=user_id)


@router.post("", response_model=ChatRead)
def create_chat(
    payload: ChatCreate,
    user_id: uuid.UUID,
    chat_service: Annotated[ChatService, Depends(get_chat_service)],
):
    return chat_service.create_chat(
        user_id=user_id,
        title=payload.title,
    )


@router.get("/{chat_id}/messages", response_model=list[ChatMessageRead])
def list_chat_messages(
    chat_id: uuid.UUID,
    user_id: uuid.UUID,
    chat_service: Annotated[ChatService, Depends(get_chat_service)],
):
    return chat_service.list_chat_messages(
        user_id=user_id,
        chat_id=chat_id,
    )


@router.post("/{chat_id}/messages", response_model=ChatMessageRead)
def create_user_message(
    chat_id: uuid.UUID,
    payload: ChatMessageCreate,
    user_id: uuid.UUID,
    chat_service: Annotated[ChatService, Depends(get_chat_service)],
):
    return chat_service.create_user_message(
        user_id=user_id,
        chat_id=chat_id,
        content=payload.content,
    )
