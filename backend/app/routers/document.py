import uuid
from typing import Annotated
from sqlalchemy.orm import Session

from fastapi import APIRouter, Depends, HTTPException, Request, status
from starlette.responses import StreamingResponse, FileResponse, Response
from starlette.concurrency import run_in_threadpool

from app.core.dependencies import require_admin
from app.core.dependencies import get_current_user, get_document_service
from app.database import get_db
from app.core.rate_limits import limit_uploads
from app.schemas.document import DocumentRead, SourcePassageRead
from app.services.document_events import document_event_broker
from app.services.document_service import DocumentService
from app.services.document_service import DocumentRetryConflict, DocumentCleanupUnavailable
from app.services.document_jobs import enqueue_document, DocumentQueueUnavailable
from app.core.logging import get_request_id
from app.models.user import User

router = APIRouter(
    prefix="/documents",
    tags=["documents"],
)


@router.delete("/{document_id}", status_code=204)
def delete_document(
    document_id: uuid.UUID,
    user: Annotated[User, Depends(require_admin)],
    service: Annotated[DocumentService, Depends(get_document_service)],
):
    try:
        service.delete_document(user.id, document_id)
        return Response(status_code=204)
    except DocumentRetryConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except DocumentCleanupUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/{document_id}/file")
def read_pdf(
    document_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    service: Annotated[DocumentService, Depends(get_document_service)],
):
    try:
        path = service.get_pdf_path(user.id, document_id)
        return FileResponse(
            path, media_type="application/pdf", filename="document.pdf",
            content_disposition_type="inline",
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        )
    except DocumentRetryConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/{document_id}/chunks/{chunk_id}", response_model=SourcePassageRead)
def read_passage(
    document_id: uuid.UUID, chunk_id: uuid.UUID,
    response: Response,
    user: Annotated[User, Depends(get_current_user)],
    service: Annotated[DocumentService, Depends(get_document_service)],
):
    try:
        response.headers["Cache-Control"] = "no-store"
        return service.get_chunk(user.id, document_id, chunk_id)
    except DocumentRetryConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


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
    db: Annotated[Session, Depends(get_db)],
):
    user_id = current_user.id
    # Authentication has finished; do not pin a database connection for the
    # lifetime of an otherwise idle Redis/SSE subscription.
    await run_in_threadpool(db.close)
    return StreamingResponse(
        document_event_broker.stream(
            user_id=user_id,
            request=request,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
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


@router.post(
    "/{document_id}/retry", response_model=DocumentRead, status_code=202,
    dependencies=[Depends(limit_uploads)],
)
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
