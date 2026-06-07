import uuid

from app.models.chat import Chat
from app.models.chat_message import ChatMessage
from app.repositories.chat_repository import ChatRepository


class ChatService:
    def __init__(self, chat_repository: ChatRepository):
        self.chat_repository = chat_repository

    def create_chat(self, user_id: uuid.UUID, title: str | None) -> Chat:
        return self.chat_repository.create_chat(
            user_id=user_id,
            title=title,
        )

    def list_user_chats(self, user_id: uuid.UUID) -> list[Chat]:
        return self.chat_repository.list_chats_by_user(user_id=user_id)

    def get_user_chat(self, user_id: uuid.UUID, chat_id: uuid.UUID) -> Chat:
        chat = self.chat_repository.get_chat_by_id(chat_id=chat_id)

        if chat is None:
            raise ValueError("Chat not found")

        if chat.user_id != user_id:
            raise PermissionError("You don't have access to this chat")

        return chat

    def create_user_message(
        self,
        user_id: uuid.UUID,
        chat_id: uuid.UUID,
        content: str,
    ) -> ChatMessage:
        self.get_user_chat(
            user_id=user_id,
            chat_id=chat_id,
        )

        message_index = self.chat_repository.get_next_message_index(
            chat_id=chat_id,
        )

        return self.chat_repository.create_message(
            chat_id=chat_id,
            message_index=message_index,
            role="user",
            content=content,
        )

    def list_chat_messages(
        self,
        user_id: uuid.UUID,
        chat_id: uuid.UUID,
    ) -> list[ChatMessage]:
        self.get_user_chat(
            user_id=user_id,
            chat_id=chat_id,
        )

        return self.chat_repository.list_messages_by_chat(
            chat_id=chat_id,
        )
