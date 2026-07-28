import uuid
from dataclasses import dataclass

from app.services.retrieval_service import RetrievedChunk


@dataclass(frozen=True)
class ContextCitation:
    source_number: int
    document_id: uuid.UUID
    chunk_id: uuid.UUID
    chunk_index: int
    page_number: int | None
    start_time_seconds: float | None
    end_time_seconds: float | None
    distance: float


@dataclass(frozen=True)
class BuiltContext:
    context: str
    citations: list[ContextCitation]


class ContextBuilderService:
    def build_context(
        self,
        retrieved_chunks: list[RetrievedChunk],
    ) -> BuiltContext:
        context_sections: list[str] = []
        citations: list[ContextCitation] = []

        for source_number, retrieved_chunk in enumerate(
            retrieved_chunks,
            start=1,
        ):
            chunk = retrieved_chunk.chunk

            context_sections.append(
                self._format_context_section(
                    source_number=source_number,
                    retrieved_chunk=retrieved_chunk,
                )
            )
            citations.append(
                ContextCitation(
                    source_number=source_number,
                    document_id=chunk.document_id,
                    chunk_id=chunk.id,
                    chunk_index=chunk.chunk_index,
                    page_number=chunk.page_number,
                    start_time_seconds=chunk.start_time_seconds,
                    end_time_seconds=chunk.end_time_seconds,
                    distance=retrieved_chunk.distance,
                )
            )

        return BuiltContext(
            context="\n\n".join(context_sections),
            citations=citations,
        )

    def _format_context_section(
        self,
        source_number: int,
        retrieved_chunk: RetrievedChunk,
    ) -> str:
        chunk = retrieved_chunk.chunk

        citation_parts = [
            f"Document ID: {chunk.document_id}",
            f"Chunk: {chunk.chunk_index}",
        ]

        if chunk.page_number is not None:
            citation_parts.append(f"Page: {chunk.page_number}")

        if chunk.start_time_seconds is not None:
            citation_parts.append(f"Start time: {chunk.start_time_seconds}")

        if chunk.end_time_seconds is not None:
            citation_parts.append(f"End time: {chunk.end_time_seconds}")

        citation_text = "\n".join(citation_parts)

        return (
            f"[Source {source_number}]\n"
            f"{citation_text}\n"
            "Content:\n"
            f"{chunk.content}"
        )
