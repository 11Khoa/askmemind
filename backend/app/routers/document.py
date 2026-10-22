import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from starlette.responses import StreamingResponse

from app.core.dependencies import get_current_user, get_document_service
from app.schemas.document import DocumentRead
from app.services.document_events import document_event_broker
from app.services.document_service import DocumentService
from app.services.document_service import DocumentRetryConflict
from app.services.document_jobs import enqueue_document, DocumentQueueUnavailable
from app.core.logging import get_request_id
from app.models.user import User

router = APIRouter(
    prefix="/documents",
    tags=["documents"],
)


@router.get("", response_model=list[DocumentRead])
def list_documents(
    current_user: Annotated[User, Depends(get_current_user)],
    document_service: Annotated[DocumentService, Depends(get_document_service)],
):
    try:
        return document_service.list_user_documents(user_id=current_user.id)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error


@router.get("/events")
async def stream_document_events(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
):
    return StreamingResponse(
        document_event_broker.stream(
            user_id=current_user.id,
            request=request,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{document_id}", response_model=DocumentRead)
def get_document(
    document_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    document_service: Annotated[DocumentService, Depends(get_document_service)],
):
    try:
        return document_service.get_user_document(
            user_id=current_user.id,
            document_id=document_id,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error


@router.post("/{document_id}/retry", response_model=DocumentRead, status_code=202)
def retry_document(
    document_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    document_service: Annotated[DocumentService, Depends(get_document_service)],
):
    try:
        document = document_service.retry_document(current_user.id, document_id)
        enqueue_document(document, document_service, get_request_id())
        return document
    except DocumentRetryConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except DocumentQueueUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
