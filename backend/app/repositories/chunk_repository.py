import uuid
from collections.abc import Sequence

from sqlalchemy.orm import Session

from app.models.chunk import Chunk


class ChunkRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_chunks(
        self,
        document_id: uuid.UUID,
        chunks_data: Sequence[dict],
    ) -> list[Chunk]:
        chunks = [
            Chunk(
                document_id=document_id,
                chunk_index=chunk_data["chunk_index"],
                content=chunk_data["content"],
                page_number=chunk_data.get("page_number"),
                start_char=chunk_data.get("start_char"),
                end_char=chunk_data.get("end_char"),
                start_time_seconds=chunk_data.get("start_time_seconds"),
                end_time_seconds=chunk_data.get("end_time_seconds"),
                chunk_metadata=chunk_data.get("chunk_metadata"),
            )
            for chunk_data in chunks_data
        ]

        self.db.add_all(chunks)
        self.db.flush()

        for chunk in chunks:
            self.db.refresh(chunk)

        return chunks

    def list_chunks_by_document(self, document_id: uuid.UUID) -> list[Chunk]:
        return (
            self.db.query(Chunk)
            .filter(Chunk.document_id == document_id)
            .order_by(Chunk.chunk_index.asc())
            .all()
        )

    def delete_chunks_by_document(self, document_id: uuid.UUID) -> int:
        delete_count = (
            self.db.query(Chunk)
            .filter(Chunk.document_id == document_id)
            .delete()
        )

        self.db.flush()

        return delete_count
