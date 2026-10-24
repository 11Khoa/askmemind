import uuid
from collections.abc import Iterator
from dataclasses import asdict, dataclass

from app.core.config import settings

from app.models.chat import Chat
from app.models.chat_message import ChatMessage
from app.repositories.chat_repository import ChatRepository
from app.repositories.user_repository import UserRepository
from app.services.rag_service import RagAnswer, RagService


@dataclass(frozen=True)
class ChatStreamEvent:
    event: str
    token: str | None = None
    message: ChatMessage | None = None


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

    def delete_chat(self, user_id: uuid.UUID, chat_id: uuid.UUID) -> None:
        chat = self.get_user_chat(user_id, chat_id, allow_admin=True)
        self.chat_repository.delete_chat(chat, actor_id=user_id)

    def get_user_chat(self, user_id: uuid.UUID, chat_id: uuid.UUID, allow_admin: bool = False) -> Chat:
        chat = self.chat_repository.get_chat_by_id(chat_id=chat_id)

        if chat is None:
            raise ValueError("Chat not found")

        requester = self.user_repository.get_user_by_id(user_id) if chat.user_id != user_id else None
        if chat.user_id != user_id and not (allow_admin and getattr(requester, "role", None) == "admin"):
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
        user_message_index = self._create_rag_user_message(
            user_id=user_id,
            chat_id=chat_id,
            content=content,
            document_id=document_id,
        )

        rag_answer = self.rag_service.answer_question(
            question=content,
            user_id=user_id,
            document_id=document_id,
            top_k=top_k,
            **self._history_options(chat_id, user_message_index, document_id),
        )

        return self._create_assistant_message(
            chat_id=chat_id,
            message_index=user_message_index + 1,
            rag_answer=rag_answer,
        )

    def stream_rag_message(
        self,
        user_id: uuid.UUID,
        chat_id: uuid.UUID,
        content: str,
        document_id: uuid.UUID | None = None,
        top_k: int = 3,
    ) -> Iterator[ChatStreamEvent]:
        user_message_index = self._create_rag_user_message(
            user_id=user_id,
            chat_id=chat_id,
            content=content,
            document_id=document_id,
        )

        for rag_event in self.rag_service.stream_answer_question(
            question=content,
            user_id=user_id,
            document_id=document_id,
            top_k=top_k,
            **self._history_options(chat_id, user_message_index, document_id),
        ):
            if rag_event.event in {"token", "replace"}:
                yield ChatStreamEvent(
                    event=rag_event.event,
                    token=rag_event.token,
                )
                continue

            if rag_event.event == "final" and rag_event.answer is not None:
                message = self._create_assistant_message(
                    chat_id=chat_id,
                    message_index=user_message_index + 1,
                    rag_answer=rag_event.answer,
                )
                yield ChatStreamEvent(event="final", message=message)

    def list_chat_messages(
        self,
        user_id: uuid.UUID,
        chat_id: uuid.UUID,
    ) -> list[ChatMessage]:
        self.get_user_chat(
            user_id=user_id,
            chat_id=chat_id,
            allow_admin=True,
        )

        return self.chat_repository.list_messages_by_chat(
            chat_id=chat_id,
        )

    def _create_rag_user_message(
        self,
        user_id: uuid.UUID,
        chat_id: uuid.UUID,
        content: str,
        document_id: uuid.UUID | None = None,
    ) -> int:
        self.get_user_chat(
            user_id=user_id,
            chat_id=chat_id,
        )

        user_message_index = self.chat_repository.get_next_message_index(
            chat_id=chat_id,
            slots=2,
        )

        self.chat_repository.create_message(
            chat_id=chat_id,
            message_index=user_message_index,
            role="user",
            content=content,
            message_metadata={"document_id": str(document_id) if document_id else None},
        )
        return user_message_index

    def _history_options(self, chat_id, before_index, document_id):
        history = self.chat_repository.conversation_history(
            chat_id, before_index, document_id,
            settings.conversation_history_turns, settings.conversation_history_characters,
        )
        return {"history": history} if history else {}

    def _create_assistant_message(
        self,
        chat_id: uuid.UUID,
        message_index: int,
        rag_answer: RagAnswer,
    ) -> ChatMessage:
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
            message_index=message_index,
            role="assistant",
            content=rag_answer.answer,
            message_metadata=message_metadata,
        )
