import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from pgvector.sqlalchemy import Vector

from app.database import Base


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    chunk_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    page_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    start_char: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    end_char: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(1536),
        nullable=True,
    )

    embedding_model: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    chunk_metadata: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
