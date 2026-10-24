import uuid

from sqlalchemy import func, update, select
from sqlalchemy.orm import Session, aliased

from app.core.types import ChatRole
from app.models.chat import Chat
from app.models.chat_message import ChatMessage
from app.models.document import Document


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

    def delete_chat(self, chat: Chat) -> None:
        self.db.delete(chat)
        self.db.commit()

    def conversation_history(self, chat_id: uuid.UUID, before_index: int,
                             document_id: uuid.UUID | None, max_turns: int,
                             max_characters: int) -> list[dict[str, str]]:
        assistant = aliased(ChatMessage)
        scope = ChatMessage.message_metadata["document_id"].as_string()
        turns = self.db.query(ChatMessage, assistant).join(
            assistant, (assistant.chat_id == ChatMessage.chat_id)
            & (assistant.message_index == ChatMessage.message_index + 1)
            & (assistant.role == "assistant"),
        ).filter(
            ChatMessage.chat_id == chat_id, ChatMessage.role == "user",
            assistant.message_index < before_index,
            scope == str(document_id) if document_id else scope.is_(None),
        ).order_by(ChatMessage.message_index.desc()).limit(max_turns).all()
        selected = []
        remaining = max_characters
        for user, answer in turns:
            if (answer.message_metadata or {}).get("sources_deleted"):
                continue
            length = len(user.content) + len(answer.content)
            if length > remaining:
                break
            selected.append((user, answer))
            remaining -= length
        return [
            {"role": message.role, "content": message.content}
            for turn in reversed(selected) for message in turn
        ]

    def list_chats_by_user(self, user_id: uuid.UUID) -> list[Chat]:
        return (
            self.db.query(Chat)
            .filter(Chat.user_id == user_id)
            .order_by(Chat.updated_at.desc())
            .all()
        )

    def get_next_message_index(self, chat_id: uuid.UUID, slots: int = 1) -> int:
        """Atomically reserve positions, releasing the row lock before LLM work.

        A question reserves two positions so its answer stays adjacent even when
        another request finishes first. Failed/cancelled requests may leave gaps.
        """
        if slots < 1:
            raise ValueError("slots must be positive")
        end_index = self.db.execute(
            update(Chat)
            .where(Chat.id == chat_id)
            .values(next_message_index=Chat.next_message_index + slots)
            .returning(Chat.next_message_index)
        ).scalar_one()
        self.db.commit()
        return end_index - slots

    def create_message(
        self,
        chat_id: uuid.UUID,
        message_index: int,
        role: ChatRole,
        content: str,
        message_metadata: dict | None = None,
    ) -> ChatMessage:
        if role == "assistant" and message_metadata:
            source_ids = {
                uuid.UUID(c["document_id"])
                for c in message_metadata.get("citations", []) if c.get("document_id")
            }
            if source_ids:
                # Serialize final persistence with deletion. A generation that
                # outlives its source must not restore deleted excerpts to chat.
                available = set(self.db.scalars(select(Document.id).where(
                    Document.id.in_(source_ids), Document.status == "ready",
                    Document.user_id == select(Chat.user_id).where(Chat.id == chat_id).scalar_subquery(),
                ).order_by(Document.id).with_for_update()).all())
                if available != source_ids:
                    content = "The source document is no longer available. Please ask again."
                    message_metadata = {"citations": [], "context": "", "sources_deleted": True}
        message = ChatMessage(
            chat_id=chat_id,
            message_index=message_index,
            role=role,
            content=content,
            message_metadata=message_metadata,
        )

        self.db.add(message)
        # Keep explicit-index imports and existing repository callers compatible.
        self.db.execute(
            update(Chat)
            .where(Chat.id == chat_id)
            .values(next_message_index=func.greatest(
                Chat.next_message_index, message_index + 1,
            ))
        )
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
