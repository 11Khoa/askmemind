import uuid
from unittest.mock import Mock

from app.services.context_builder_service import (
    BuiltContext,
    ContextBuilderService,
    ContextCitation,
)
from app.services.retrieval_service import RetrievedChunk


def test_build_context_formats_pdf_chunks_with_citations() -> None:
    document_id = uuid.uuid4()
    chunk_id = uuid.uuid4()

    chunk = Mock()
    chunk.id = chunk_id
    chunk.document_id = document_id
    chunk.chunk_index = 0
    chunk.page_number = 3
    chunk.start_time_seconds = None
    chunk.end_time_seconds = None
    chunk.content = "Refunds are available within 30 days."

    retrieved_chunk = RetrievedChunk(
        chunk=chunk,
        distance=0.12,
    )

    service = ContextBuilderService()

    result = service.build_context(
        retrieved_chunks=[retrieved_chunk],
    )

    assert isinstance(result, BuiltContext)
    assert result.context == (
        "[Source 1]\n"
        f"Document ID: {document_id}\n"
        "Chunk: 0\n"
        "Page: 3\n"
        "Content:\n"
        "Refunds are available within 30 days."
    )
    assert result.citations == [
        ContextCitation(
            source_number=1,
            document_id=document_id,
            chunk_id=chunk_id,
            chunk_index=0,
            page_number=3,
            start_time_seconds=None,
            end_time_seconds=None,
            distance=0.12,
        )
    ]


def test_build_context_numbers_multiple_sources() -> None:
    first_document_id = uuid.uuid4()
    second_document_id = uuid.uuid4()

    first_chunk = Mock()
    first_chunk.id = uuid.uuid4()
    first_chunk.document_id = first_document_id
    first_chunk.chunk_index = 0
    first_chunk.page_number = 1
    first_chunk.start_time_seconds = None
    first_chunk.end_time_seconds = None
    first_chunk.content = "First chunk content."

    second_chunk = Mock()
    second_chunk.id = uuid.uuid4()
    second_chunk.document_id = second_document_id
    second_chunk.chunk_index = 1
    second_chunk.page_number = 2
    second_chunk.start_time_seconds = None
    second_chunk.end_time_seconds = None
    second_chunk.content = "Second chunk content."

    service = ContextBuilderService()

    result = service.build_context(
        retrieved_chunks=[
            RetrievedChunk(chunk=first_chunk, distance=0.1),
            RetrievedChunk(chunk=second_chunk, distance=0.2),
        ],
    )

    assert "[Source 1]" in result.context
    assert "[Source 2]" in result.context
    assert "First chunk content." in result.context
    assert "Second chunk content." in result.context
    assert [citation.source_number for citation in result.citations] == [1, 2]


def test_build_context_includes_timestamp_citations_when_present() -> None:
    document_id = uuid.uuid4()
    chunk_id = uuid.uuid4()

    chunk = Mock()
    chunk.id = chunk_id
    chunk.document_id = document_id
    chunk.chunk_index = 4
    chunk.page_number = None
    chunk.start_time_seconds = 12.5
    chunk.end_time_seconds = 18.0
    chunk.content = "Transcript segment content."

    service = ContextBuilderService()

    result = service.build_context(
        retrieved_chunks=[
            RetrievedChunk(chunk=chunk, distance=0.3),
        ],
    )

    assert result.context == (
        "[Source 1]\n"
        f"Document ID: {document_id}\n"
        "Chunk: 4\n"
        "Start time: 12.5\n"
        "End time: 18.0\n"
        "Content:\n"
        "Transcript segment content."
    )
    assert result.citations == [
        ContextCitation(
            source_number=1,
            document_id=document_id,
            chunk_id=chunk_id,
            chunk_index=4,
            page_number=None,
            start_time_seconds=12.5,
            end_time_seconds=18.0,
            distance=0.3,
        )
    ]
