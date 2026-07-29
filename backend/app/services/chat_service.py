import uuid
from dataclasses import asdict

from app.models.chat import Chat
from app.models.chat_message import ChatMessage
from app.repositories.chat_repository import ChatRepository
from app.repositories.user_repository import UserRepository
from app.services.rag_service import RagService


class ChatService:
    def __init__(
        self,
        chat_repository: ChatRepository,
        user_repository: UserRepository,
        rag_service: RagService,
    ) -> None:
        self.chat_repository = chat_repository
        self.user_repository = user_repository
        self.rag_service = rag_service

    def create_chat(self, user_id: uuid.UUID, title: str | None) -> Chat:
        user = self.user_repository.get_user_by_id(user_id)
        if user is None:
            raise ValueError("User not found")

        return self.chat_repository.create_chat(
            user_id=user_id,
            title=title,
        )

    def list_user_chats(self, user_id: uuid.UUID) -> list[Chat]:
        user = self.user_repository.get_user_by_id(user_id)
        if user is None:
            raise ValueError("User not found")

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

    def create_rag_message(
        self,
        user_id: uuid.UUID,
        chat_id: uuid.UUID,
        content: str,
        document_id: uuid.UUID | None = None,
        top_k: int = 3,
    ) -> ChatMessage:
        self.get_user_chat(
            user_id=user_id,
            chat_id=chat_id,
        )

        user_message_index = self.chat_repository.get_next_message_index(
            chat_id=chat_id,
        )

        self.chat_repository.create_message(
            chat_id=chat_id,
            message_index=user_message_index,
            role="user",
            content=content,
        )

        rag_answer = self.rag_service.answer_question(
            question=content,
            user_id=user_id,
            document_id=document_id,
            top_k=top_k,
        )

        message_metadata = {
            "citations": [
                {
                    **asdict(citation),
                    "document_id": str(citation.document_id),
                    "chunk_id": str(citation.chunk_id),
                }
                for citation in rag_answer.citations
            ],
            "context": rag_answer.context,
        }

        return self.chat_repository.create_message(
            chat_id=chat_id,
            message_index=user_message_index + 1,
            role="assistant",
            content=rag_answer.answer,
            message_metadata=message_metadata,
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
