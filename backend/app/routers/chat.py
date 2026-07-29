import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.dependencies import get_chat_service, get_current_user
from app.schemas.chat import (
    ChatCreate,
    ChatMessageCreate,
    ChatMessageRead,
    ChatQuestionCreate,
    ChatRead,
)
from app.services.chat_service import ChatService
from app.models.user import User

router = APIRouter(
    prefix="/chats",
    tags=["chats"],
)


@router.get("", response_model=list[ChatRead])
def list_chats(
    current_user: Annotated[User, Depends(get_current_user)],
    chat_service: Annotated[ChatService, Depends(get_chat_service)],
):
    try:
        return chat_service.list_user_chats(user_id=current_user.id)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error


@router.post("", response_model=ChatRead)
def create_chat(
    payload: ChatCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    chat_service: Annotated[ChatService, Depends(get_chat_service)],
):
    try:
        return chat_service.create_chat(
            user_id=current_user.id,
            title=payload.title,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error


@router.get("/{chat_id}/messages", response_model=list[ChatMessageRead])
def list_chat_messages(
    chat_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    chat_service: Annotated[ChatService, Depends(get_chat_service)],
):

    try:
        return chat_service.list_chat_messages(
            user_id=current_user.id,
            chat_id=chat_id,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error
    except PermissionError as error:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(error),
        ) from error


@router.post("/{chat_id}/messages", response_model=ChatMessageRead)
def create_user_message(
    chat_id: uuid.UUID,
    payload: ChatMessageCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    chat_service: Annotated[ChatService, Depends(get_chat_service)],
):
    try:
        return chat_service.create_user_message(
            user_id=current_user.id,
            chat_id=chat_id,
            content=payload.content,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error
    except PermissionError as error:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(error),
        ) from error


@router.post("/{chat_id}/questions", response_model=ChatMessageRead)
def create_rag_question(
    chat_id: uuid.UUID,
    payload: ChatQuestionCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    chat_service: Annotated[ChatService, Depends(get_chat_service)],
):
    try:
        return chat_service.create_rag_message(
            user_id=current_user.id,
            chat_id=chat_id,
            content=payload.content,
            document_id=payload.document_id,
            top_k=payload.top_k,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error
    except PermissionError as error:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(error),
        ) from error
