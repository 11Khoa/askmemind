import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.dependencies import get_current_user, get_document_service
from app.schemas.document import DocumentRead
from app.services.document_service import DocumentService
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
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(error),
        ) from error
