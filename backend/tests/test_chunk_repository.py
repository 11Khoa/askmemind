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


def make_embedding(index: int) -> list[float]:
    embedding = [0.0] * 1024
    embedding[index] = 1.0
    return embedding


def test_search_similar_chunks_returns_chunks_ordered_by_cosine_distance(
    db_session: Session,
) -> None:
    user = User(
        email="chunk-vector-search@gmail.com",
        hashed_password="hashed",
    )

    document = Document(
        filename="vector-search-test.pdf",
        original_filename="vector-search-test.pdf",
        file_path="/tmp/vector-search-test.pdf",
        content_type="application/pdf",
        file_size_bytes=500,
    )

    user.documents.append(document)
    db_session.add(user)
    db_session.flush()

    repository = ChunkRepository(db_session)

    repository.create_chunks(
        document_id=document.id,
        chunks_data=[
            {
                "chunk_index": 0,
                "content": "Most relevant chunk",
                "embedding": make_embedding(0),
                "embedding_provider": "test-provider",
                "embedding_model": "test-model",
                "embedding_dimensions": 1024,
            },
            {
                "chunk_index": 1,
                "content": "Less relevant chunk",
                "embedding": make_embedding(1),
                "embedding_provider": "test-provider",
                "embedding_model": "test-model",
                "embedding_dimensions": 1024,
            },
            {
                "chunk_index": 2,
                "content": "Another less relevant chunk",
                "embedding": make_embedding(2),
                "embedding_provider": "test-provider",
                "embedding_model": "test-model",
                "embedding_dimensions": 1024,
            },
        ],
    )

    results = repository.search_similar_chunks(
        embedding=make_embedding(0),
        user_id=user.id,
        top_k=2,
    )
    assert len(results) == 2
    assert results[0][0].content == "Most relevant chunk"
    assert results[0][1] == 0


def test_search_similar_chunks_filters_by_document_id(
    db_session: Session,
) -> None:
    user = User(
        email="chunk-vector-filter@gmail.com",
        hashed_password="hashed",
    )

    first_document = Document(
        filename="first-vector-search.pdf",
        original_filename="first-vector-search.pdf",
        file_path="/tmp/first-vector-search.pdf",
        content_type="application/pdf",
        file_size_bytes=500,
    )

    second_document = Document(
        filename="second-vector-search.pdf",
        original_filename="second-vector-search.pdf",
        file_path="/tmp/second-vector-search.pdf",
        content_type="application/pdf",
        file_size_bytes=500,
    )

    user.documents.append(first_document)
    user.documents.append(second_document)
    db_session.add(user)
    db_session.flush()

    repository = ChunkRepository(db_session)

    repository.create_chunks(
        document_id=first_document.id,
        chunks_data=[
            {
                "chunk_index": 0,
                "content": "First document chunk",
                "embedding": make_embedding(0),
                "embedding_provider": "test-provider",
                "embedding_model": "test-model",
                "embedding_dimensions": 1024,
            },
        ],
    )

    repository.create_chunks(
        document_id=second_document.id,
        chunks_data=[
            {
                "chunk_index": 0,
                "content": "Second document chunk",
                "embedding": make_embedding(0),
                "embedding_provider": "test-provider",
                "embedding_model": "test-model",
                "embedding_dimensions": 1024,
            },
        ],
    )

    results = repository.search_similar_chunks(
        embedding=make_embedding(0),
        user_id=user.id,
        document_id=second_document.id,
        top_k=5,
    )

    assert len(results) == 1
    assert results[0][0].document_id == second_document.id
    assert results[0][0].content == "Second document chunk"

def test_search_similar_chunks_searches_all_documents_for_one_user(
    db_session: Session,
) -> None:
    first_user = User(
        email="chunk-vector-user-scope-first@gmail.com",
        hashed_password="hashed",
    )
    second_user = User(
        email="chunk-vector-user-scope-second@gmail.com",
        hashed_password="hashed",
    )

    first_user_document = Document(
        filename="first-user-vector-search.pdf",
        original_filename="first-user-vector-search.pdf",
        file_path="/tmp/first-user-vector-search.pdf",
        content_type="application/pdf",
        file_size_bytes=500,
    )
    first_user_second_document = Document(
        filename="first-user-second-vector-search.pdf",
        original_filename="first-user-second-vector-search.pdf",
        file_path="/tmp/first-user-second-vector-search.pdf",
        content_type="application/pdf",
        file_size_bytes=500,
    )
    second_user_document = Document(
        filename="second-user-vector-search.pdf",
        original_filename="second-user-vector-search.pdf",
        file_path="/tmp/second-user-vector-search.pdf",
        content_type="application/pdf",
        file_size_bytes=500,
    )

    first_user.documents.append(first_user_document)
    first_user.documents.append(first_user_second_document)
    second_user.documents.append(second_user_document)
    db_session.add(first_user)
    db_session.add(second_user)
    db_session.flush()

    repository = ChunkRepository(db_session)

    repository.create_chunks(
        document_id=first_user_document.id,
        chunks_data=[
            {
                "chunk_index": 0,
                "content": "First user first document chunk",
                "embedding": make_embedding(0),
                "embedding_provider": "test-provider",
                "embedding_model": "test-model",
                "embedding_dimensions": 1024,
            },
        ],
    )
    repository.create_chunks(
        document_id=first_user_second_document.id,
        chunks_data=[
            {
                "chunk_index": 0,
                "content": "First user second document chunk",
                "embedding": make_embedding(1),
                "embedding_provider": "test-provider",
                "embedding_model": "test-model",
                "embedding_dimensions": 1024,
            },
        ],
    )
    repository.create_chunks(
        document_id=second_user_document.id,
        chunks_data=[
            {
                "chunk_index": 0,
                "content": "Second user document chunk",
                "embedding": make_embedding(0),
                "embedding_provider": "test-provider",
                "embedding_model": "test-model",
                "embedding_dimensions": 1024,
            },
        ],
    )

    results = repository.search_similar_chunks(
        embedding=make_embedding(0),
        user_id=first_user.id,
        top_k=5,
    )

    result_contents = [chunk.content for chunk, _distance in results]

    assert result_contents == [
        "First user first document chunk",
        "First user second document chunk",
    ]
