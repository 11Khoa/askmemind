import uuid
import jwt
from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.repositories.chat_repository import ChatRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.user_repository import UserRepository
from app.services.auth_service import AuthService
from app.services.chat_service import ChatService
from app.services.document_service import DocumentService
from app.models.user import User
from app.core.security import decode_access_token


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_chat_service(
    db: Annotated[Session, Depends(get_db)],
) -> ChatService:
    user_repository = UserRepository(db=db)
    chat_repository = ChatRepository(db=db)
    return ChatService(
        chat_repository=chat_repository,
        user_repository=user_repository,
    )


def get_auth_service(
    db: Annotated[Session, Depends(get_db)],
) -> AuthService:
    user_repository = UserRepository(db=db)
    return AuthService(user_repository=user_repository)


def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    try:
        subject = decode_access_token(token)
        user_id = uuid.UUID(subject)
    except (ValueError, jwt.PyJWTError) as error:
        raise HTTPException(
            status_code=401,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from error

    user_repository = UserRepository(db=db)
    user = user_repository.get_user_by_id(user_id)

    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


def get_document_service(
    db: Annotated[Session, Depends(get_db)],
) -> DocumentService:
    user_repository = UserRepository(db=db)
    document_repository = DocumentRepository(db=db)

    return DocumentService(
        document_repository=document_repository,
        user_repository=user_repository,
    )
