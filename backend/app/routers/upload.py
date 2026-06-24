import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, status, UploadFile

from app.core.config import settings
from app.core.dependencies import get_current_user, get_document_service
from app.schemas.document import DocumentRead
from app.services.document_service import DocumentService
from app.models.user import User


router = APIRouter(
    prefix="/documents",
    tags=["documents"],
)


@router.post("/upload", response_model=DocumentRead)
def upload_document(
    file: Annotated[UploadFile, File()],
    current_user: Annotated[User, Depends(get_current_user)],
    document_service: Annotated[DocumentService, Depends(get_document_service)],
):
    file_bytes = file.file.read()
    file_size_bytes = len(file_bytes)

    original_filename = file.filename or "upload.pdf"
    filename = f"{uuid.uuid4()}.pdf"
    file_path = str(Path(settings.upload_dir) / filename)

    try:
        return document_service.create_uploaded_document(
            user_id=current_user.id,
            filename=filename,
            original_filename=original_filename,
            file_path=file_path,
            content_type=file.content_type or "",
            file_size_bytes=file_size_bytes,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error
