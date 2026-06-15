from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.repositories.chat_repository import ChatRepository
from app.repositories.user_repository import UserRepository
from app.services.auth_service import AuthService
from app.services.chat_service import ChatService


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
