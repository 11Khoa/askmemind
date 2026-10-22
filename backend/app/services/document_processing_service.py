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
        embedding_batch_size: int = 32,
    ) -> None:
        if embedding_batch_size < 1:
            raise ValueError("Embedding batch size must be positive")
        self.extraction_service = extraction_service
        self.chunking_service = chunking_service
        self.embedding_service = embedding_service
        self.chunk_persistence_service = chunk_persistence_service
        self.document_repository = document_repository
        self.unit_of_work = unit_of_work
        self.embedding_batch_size = embedding_batch_size

    def _has_current_embedding(self, chunk: Chunk) -> bool:
        service = self.embedding_service
        return (
            chunk.embedding_v2 is not None
            and len(chunk.embedding_v2) == service.embedding_dimensions
            and chunk.embedding_v2_provider == service.embedding_provider
            and chunk.embedding_v2_model == service.embedding_model
            and chunk.embedding_v2_dimensions == service.embedding_dimensions
        )

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
            chunks = self.chunk_persistence_service.list_chunks(document_id)
            complete = (
                document.chunk_count is not None
                and document.chunk_count > 0
                and len(chunks) == document.chunk_count
                and [chunk.chunk_index for chunk in chunks]
                == list(range(document.chunk_count))
            )
            if not complete:
                # Legacy rows alone do not prove extraction/chunking finished.
                if not file_path.is_file():
                    raise ValueError("Original PDF is unavailable. Upload it again.")
                source = self.extraction_service.extract(file_path=file_path)
                text_chunks = self.chunking_service.chunk_source(source=source)
                if not text_chunks:
                    raise ValueError("PDF contains no extractable text")
                chunks = self.chunk_persistence_service.prepare_chunks(
                    document_id, text_chunks
                )
                document.page_count = source.metadata.get("page_count")
                document.chunk_count = len(chunks)
                self.unit_of_work.commit()

            pending = [
                chunk for chunk in chunks if not self._has_current_embedding(chunk)
            ]
            for start in range(0, len(pending), self.embedding_batch_size):
                batch = pending[start : start + self.embedding_batch_size]
                embeddings = self.embedding_service.embed_passages(
                    texts=[chunk.content for chunk in batch]
                )
                self.chunk_persistence_service.save_embeddings(
                    batch,
                    embeddings,
                    self.embedding_service.embedding_provider,
                    self.embedding_service.embedding_model,
                    self.embedding_service.embedding_dimensions,
                )
                # Successful batches survive a later provider/worker failure.
                self.unit_of_work.commit()
            self.document_repository.mark_processing_completed(
                document=document,
                page_count=document.page_count,
            )

            self.unit_of_work.commit()

            return chunks

        except Exception as error:
            self.unit_of_work.rollback()

            self.document_repository.mark_processing_failed(
                document=document,
                error_message=str(error),
            )

            self.unit_of_work.commit()

            raise
