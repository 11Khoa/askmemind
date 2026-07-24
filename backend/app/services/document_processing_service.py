import uuid
from pathlib import Path

from app.core.unit_of_work import UnitOfWork
from app.models.chunk import Chunk
from app.services.chunk_persistence_service import ChunkPersistenceService
from app.services.chunk_service import ChunkingService
from app.services.extraction.base import SourceExtractionService


class DocumentProcessingService:
    def __init__(
        self,
        extraction_service: SourceExtractionService,
        chunking_service: ChunkingService,
        chunk_persistence_service: ChunkPersistenceService,
        unit_of_work: UnitOfWork,
    ) -> None:
        self.extraction_service = extraction_service
        self.chunking_service = chunking_service
        self.chunk_persistence_service = chunk_persistence_service
        self.unit_of_work = unit_of_work

    def process_document(
        self,
        document_id: uuid.UUID,
        file_path: Path,
    ) -> list[Chunk]:
        try:
            extracted_source = self.extraction_service.extract(
                file_path=file_path,
            )

            text_chunks = self.chunking_service.chunk_source(
                source=extracted_source,
            )

            persisted_chunks = self.chunk_persistence_service.persist_chunks(
                document_id=document_id,
                text_chunks=text_chunks,
            )

            self.unit_of_work.commit()

            return persisted_chunks

        except Exception:
            self.unit_of_work.rollback()
            raise
