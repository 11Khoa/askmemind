import json
import logging
import uuid
from collections.abc import Iterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse, Response

from app.core.dependencies import get_chat_service, get_current_user
from app.core.logging import get_request_id
from app.core.rate_limits import limit_questions
from app.schemas.chat import (
    ChatCreate,
    ChatMessageCreate,
    ChatMessageRead,
    ChatQuestionCreate,
    ChatRead,
)
from app.services.chat_service import ChatService
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/chats",
    tags=["chats"],
)


def _sse_event(event: str, data: dict[str, Any]) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


@router.delete("/{chat_id}", status_code=204)
def delete_chat(
    chat_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    service: Annotated[ChatService, Depends(get_chat_service)],
):
    try:
        service.delete_chat(user.id, chat_id)
        return Response(status_code=204)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error


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


@router.post(
    "/{chat_id}/messages", response_model=ChatMessageRead,
    dependencies=[Depends(limit_questions)],
)
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


@router.post(
    "/{chat_id}/questions", response_model=ChatMessageRead,
    dependencies=[Depends(limit_questions)],
)
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


@router.post("/{chat_id}/questions/stream", dependencies=[Depends(limit_questions)])
def stream_rag_question(
    chat_id: uuid.UUID,
    payload: ChatQuestionCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    chat_service: Annotated[ChatService, Depends(get_chat_service)],
):
    try:
        chat_service.get_user_chat(
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

    def events() -> Iterator[str]:
        try:
            for stream_event in chat_service.stream_rag_message(
                user_id=current_user.id,
                chat_id=chat_id,
                content=payload.content,
                document_id=payload.document_id,
                top_k=payload.top_k,
            ):
                if stream_event.event in {"token", "replace"}:
                    yield _sse_event(
                        stream_event.event,
                        {"token": stream_event.token or ""},
                    )
                elif stream_event.event == "final" and stream_event.message:
                    message = ChatMessageRead.model_validate(
                        stream_event.message,
                    ).model_dump(mode="json")
                    yield _sse_event("final", message)
        except Exception:
            logger.exception("chat.stream.failed")
            yield _sse_event("error", {
                "detail": "Could not generate answer. Please try again.",
                "request_id": get_request_id(),
            })

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
