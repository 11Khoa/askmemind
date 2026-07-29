import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.core.types import ChatRole


class ChatCreate(BaseModel):
    title: str | None = Field(
        default=None,
        max_length=255,
    )


class ChatRead(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    title: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ChatMessageCreate(BaseModel):
    content: str = Field(
        min_length=1,
    )


class ChatQuestionCreate(BaseModel):
    content: str = Field(
        min_length=1,
    )
    document_id: uuid.UUID | None = None
    top_k: int = Field(
        default=3,
        ge=1,
        le=10,
    )


class ChatMessageRead(BaseModel):
    id: uuid.UUID
    chat_id: uuid.UUID
    message_index: int
    role: ChatRole
    content: str
    message_metadata: dict[str, Any] | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ChatWithMessagesRead(ChatRead):
    messages: list[ChatMessageRead]
