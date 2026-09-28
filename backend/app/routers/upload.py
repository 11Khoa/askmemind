import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, status, UploadFile
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.core.dependencies import (
    get_current_user,
    get_document_processing_service,
    get_document_service,
    get_file_storage_service,
)
from app.schemas.document import DocumentRead
from app.services.document_processing_service import DocumentProcessingService
from app.services.document_service import DocumentService
from app.services.file_storage_service import FileStorageService
from app.models.user import User


router = APIRouter(
    prefix="/documents",
    tags=["documents"],
)


def _read_validated_pdf(
    file: UploadFile,
    max_size_bytes: int,
) -> bytes:
    if file.content_type != "application/pdf":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF uploads are supported",
        )

    file_bytes = file.file.read(max_size_bytes + 1)
    if len(file_bytes) > max_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Uploaded PDF exceeds the configured size limit",
        )

    if not file_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded PDF is empty",
        )

    if not file_bytes.startswith(b"%PDF-"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file does not have a valid PDF header",
        )

    return file_bytes




@router.post("/upload", response_model=DocumentRead)
def upload_document(
    file: Annotated[UploadFile, File()],
    current_user: Annotated[User, Depends(get_current_user)],
    document_service: Annotated[DocumentService, Depends(get_document_service)],
    file_storage_service: Annotated[FileStorageService, Depends(get_file_storage_service)],
    document_processing_service: Annotated[
        DocumentProcessingService,
        Depends(get_document_processing_service),
    ],
):
    file_bytes = _read_validated_pdf(
        file=file,
        max_size_bytes=settings.max_upload_size_mb * 1024 * 1024,
    )
    file_size_bytes = len(file_bytes)

    original_filename = file.filename or "upload.pdf"
    filename = f"{uuid.uuid4()}.pdf"
    file_path = file_storage_service.save_upload(
        file_bytes=file_bytes,
        filename=filename,
    )

    try:
        document = document_service.create_uploaded_document(
            user_id=current_user.id,
            filename=filename,
            original_filename=original_filename,
            file_path=file_path,
            content_type=file.content_type or "",
            file_size_bytes=file_size_bytes,
        )
    except ValueError as error:
        file_storage_service.delete_file(file_path=file_path)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error
    except SQLAlchemyError as error:
        file_storage_service.delete_file(file_path=file_path)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not save uploaded document",
        ) from error

    try:
        document_processing_service.process_document(
            document_id=document.id,
            file_path=Path(file_path),
        )
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not process uploaded document",
        ) from error

    return document_service.get_user_document(
        user_id=current_user.id,
        document_id=document.id,
    )
