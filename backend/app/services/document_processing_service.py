import uuid
from pathlib import Path

from app.core.unit_of_work import UnitOfWork
from app.models.chunk import Chunk
from app.repositories.document_repository import DocumentRepository
from app.services.chunk_persistence_service import ChunkPersistenceService
from app.services.chunk_service import ChunkingService
from app.services.embedding_service import EmbeddingService
from app.services.extraction.base import SourceExtractionService


class DocumentProcessingService:
    def __init__(
        self,
        extraction_service: SourceExtractionService,
        chunking_service: ChunkingService,
        embedding_service: EmbeddingService,
        chunk_persistence_service: ChunkPersistenceService,
        document_repository: DocumentRepository,
        unit_of_work: UnitOfWork,
    ) -> None:
        self.extraction_service = extraction_service
        self.chunking_service = chunking_service
        self.embedding_service = embedding_service
        self.chunk_persistence_service = chunk_persistence_service
        self.document_repository = document_repository
        self.unit_of_work = unit_of_work

    def process_document(
        self,
        document_id: uuid.UUID,
        file_path: Path,
    ) -> list[Chunk]:
        document = self.document_repository.get_document_by_id(
            document_id=document_id,
        )

        if document is None:
            raise ValueError("Document not found")

        self.document_repository.mark_processing_started(document=document)
        self.unit_of_work.commit()

        try:
            extracted_source = self.extraction_service.extract(
                file_path=file_path,
            )

            text_chunks = self.chunking_service.chunk_source(
                source=extracted_source,
            )

            embeddings = self.embedding_service.embed_passages(
                texts=[
                    text_chunk.content
                    for text_chunk in text_chunks
                ],
            )

            persisted_chunks = self.chunk_persistence_service.persist_chunks(
                document_id=document_id,
                text_chunks=text_chunks,
                embeddings=embeddings,
                embedding_provider=self.embedding_service.embedding_provider,
                embedding_model=self.embedding_service.embedding_model,
                embedding_dimensions=self.embedding_service.embedding_dimensions,
            )

            page_count = extracted_source.metadata.get("page_count")

            self.document_repository.mark_processing_completed(
                document=document,
                page_count=page_count,
            )

            self.unit_of_work.commit()

            return persisted_chunks

        except Exception as error:
            self.unit_of_work.rollback()

            self.document_repository.mark_processing_failed(
                document=document,
                error_message=str(error),
            )

            self.unit_of_work.commit()

            raise
