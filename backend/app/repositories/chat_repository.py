import uuid

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.types import ChatRole
from app.models.chat import Chat
from app.models.chat_message import ChatMessage


class ChatRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_chat(self, user_id: uuid.UUID, title: str | None) -> Chat:
        chat = Chat(
            user_id=user_id,
            title=title,
        )

        self.db.add(chat)
        self.db.commit()
        self.db.refresh(chat)

        return chat

    def get_chat_by_id(self, chat_id: uuid.UUID) -> Chat | None:
        return self.db.get(Chat, chat_id)

    def list_chats_by_user(self, user_id: uuid.UUID) -> list[Chat]:
        return (
            self.db.query(Chat)
            .filter(Chat.user_id == user_id)
            .order_by(Chat.updated_at.desc())
            .all()
        )

    def get_next_message_index(self, chat_id: uuid.UUID) -> int:
        max_index = (
            self.db.query(func.max(ChatMessage.message_index))
            .filter(ChatMessage.chat_id == chat_id)
            .scalar()
        )

        if max_index is None:
            return 0

        return max_index + 1

    def create_message(
        self,
        chat_id: uuid.UUID,
        message_index: int,
        role: ChatRole,
        content: str,
        message_metadata: dict | None = None,
    ) -> ChatMessage:
        message = ChatMessage(
            chat_id=chat_id,
            message_index=message_index,
            role=role,
            content=content,
            message_metadata=message_metadata,
        )

        self.db.add(message)
        self.db.commit()
        self.db.refresh(message)

        return message

    def list_messages_by_chat(self, chat_id: uuid.UUID) -> list[ChatMessage]:
        return (
            self.db.query(ChatMessage)
            .filter(ChatMessage.chat_id == chat_id)
            .order_by(ChatMessage.message_index.asc())
            .all()
        )
