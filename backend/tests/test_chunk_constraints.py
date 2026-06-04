import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.chunk import Chunk
from app.models.document import Document
from app.models.user import User


def test_document_cannot_have_duplicate_chunk_indexes(db_session: Session) -> None:
    user = User(
        email="duplicate-chunk@gmail.com",
        hashed_password="hashed",
    )

    document = Document(
        filename="duplicate.pdf",
        original_filename="duplicate.pdf",
        file_path="/tmp/duplicate.pdf",
        content_type="application/pdf",
        file_size_bytes=123,
    )

    first_chunk = Chunk(
        chunk_index=0,
        content="First chunk",
        page_number=1,
    )

    duplicate_chunk = Chunk(
        chunk_index=0,
        content="Duplicate chunk",
        page_number=1,
    )

    user.documents.append(document)
    document.chunks.append(first_chunk)
    document.chunks.append(duplicate_chunk)

    db_session.add(user)

    with pytest.raises(IntegrityError):
        db_session.commit()
