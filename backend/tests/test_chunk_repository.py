from sqlalchemy.orm import Session

from app.models.chunk import Chunk
from app.models.document import Document
from app.models.user import User
from app.repositories.chunk_repository import ChunkRepository


def test_create_chunks_preserves_content_and_citations(db_session: Session) -> None:
    user = User(
        email="chunk-repository-create@gmail.com",
        hashed_password="hashed",
    )

    document = Document(
        filename="repository-test.pdf",
        original_filename="repository-test.pdf",
        file_path="/tmp/repository-test.pdf",
        content_type="application/pdf",
        file_size_bytes=500,
    )

    user.documents.append(document)
    db_session.add(user)
    db_session.flush()

    repository = ChunkRepository(db_session)

    chunks_data = [
        {
            "chunk_index": 0,
            "content": "Content from the first PDF page.",
            "page_number": 1,
            "start_char": 0,
            "end_char": 32,
            "chunk_metadata": {"section": "introduction"},
        },
        {
            "chunk_index": 1,
            "content": "Content from the second PDF page.",
            "page_number": 2,
            "start_char": 10,
            "end_char": 43,
            "chunk_metadata": {"section": "details"},
        },
    ]

    created_chunks = repository.create_chunks(
        document_id=document.id,
        chunks_data=chunks_data,
    )

    assert len(created_chunks) == 2

    first_chunk = created_chunks[0]
    second_chunk = created_chunks[1]

    assert first_chunk.id is not None
    assert first_chunk.document_id == document.id
    assert first_chunk.chunk_index == 0
    assert first_chunk.content == "Content from the first PDF page."
    assert first_chunk.page_number == 1
    assert first_chunk.start_char == 0
    assert first_chunk.end_char == 32
    assert first_chunk.chunk_metadata == {"section": "introduction"}

    assert second_chunk.id is not None
    assert second_chunk.document_id == document.id
    assert second_chunk.chunk_index == 1
    assert second_chunk.content == "Content from the second PDF page."
    assert second_chunk.page_number == 2
    assert second_chunk.start_char == 10
    assert second_chunk.end_char == 43
    assert second_chunk.chunk_metadata == {"section": "details"}

    persisted_chunks = (
        db_session.query(Chunk)
        .filter(Chunk.document_id == document.id)
        .all()
    )

    assert len(persisted_chunks) == 2


def test_list_chunks_by_document_orders_by_chunk_index(db_session: Session) -> None:
    user = User(
        email="chunks-list@gmail.com",
        hashed_password="hashed",
    )

    document = Document(
        filename="chunks-list-test.pdf",
        original_filename="chunks-list-test.pdf",
        file_path="/tmp/chunks-list-test.pdf",
        content_type="application/pdf",
        file_size_bytes=500,
    )

    user.documents.append(document)
    db_session.add(user)
    db_session.flush()

    repository = ChunkRepository(db_session)

    chunks_data = [
        {
            "chunk_index": 2,
            "content": "Content from the third PDF page.",
            "page_number": 3,
            "start_char": 20,
            "end_char": 53,
            "chunk_metadata": {"section": "details"},
        },
        {
            "chunk_index": 0,
            "content": "Content from the first PDF page.",
            "page_number": 1,
            "start_char": 0,
            "end_char": 32,
            "chunk_metadata": {"section": "introduction"},
        },
        {
            "chunk_index": 1,
            "content": "Content from the second PDF page.",
            "page_number": 2,
            "start_char": 10,
            "end_char": 43,
            "chunk_metadata": {"section": "details"},
        },
    ]

    repository.create_chunks(
        document_id=document.id,
        chunks_data=chunks_data,
    )

    listed_chunks = repository.list_chunks_by_document(document_id=document.id)
    chunk_indexes = [chunk.chunk_index for chunk in listed_chunks]

    assert chunk_indexes == [0, 1, 2]


def test_delete_chunks_by_document_deletes_only_selected_document(db_session: Session) -> None:
    user = User(
        email="delete-chunk@gmail.com",
        hashed_password="hashed",
    )

    document_first = Document(
        filename="chunks-first-delete-test.pdf",
        original_filename="chunks-first-delete-test.pdf",
        file_path="/tmp/chunks-first-delete-test.pdf",
        content_type="application/pdf",
        file_size_bytes=500,
    )

    document_second = Document(
        filename="chunks-second-delete-test.pdf",
        original_filename="chunks-second-delete-test.pdf",
        file_path="/tmp/chunks-second-delete-test.pdf",
        content_type="application/pdf",
        file_size_bytes=500,
    )

    user.documents.append(document_first)
    user.documents.append(document_second)
    db_session.add(user)
    db_session.flush()

    repository = ChunkRepository(db_session)

    chunks_first_data = [
        {
            "chunk_index": 0,
            "content": "Content document first from the first PDF page.",
            "page_number": 1,
            "start_char": 0,
            "end_char": 32,
            "chunk_metadata": {"section": "introduction"},
        },
        {
            "chunk_index": 1,
            "content": "Content document first from the second PDF page.",
            "page_number": 2,
            "start_char": 10,
            "end_char": 43,
            "chunk_metadata": {"section": "details"},
        },
    ]

    chunks_second_data = [
        {
            "chunk_index": 0,
            "content": "Content document second from the first PDF page.",
            "page_number": 1,
            "start_char": 0,
            "end_char": 32,
            "chunk_metadata": {"section": "introduction"},
        },
    ]

    repository.create_chunks(
        document_id=document_first.id,
        chunks_data=chunks_first_data,
    )

    repository.create_chunks(
        document_id=document_second.id,
        chunks_data=chunks_second_data,
    )

    deleted_count = repository.delete_chunks_by_document(
        document_id=document_first.id,
    )

    first_document_chunks = repository.list_chunks_by_document(
        document_id=document_first.id,
    )

    second_document_chunks = repository.list_chunks_by_document(
        document_id=document_second.id,
    )
    
    assert deleted_count == 2
    assert first_document_chunks == []

    assert len(second_document_chunks) == 1
    assert second_document_chunks[0].document_id == document_second.id
    assert (
        second_document_chunks[0].content
        == "Content document second from the first PDF page."
    )
