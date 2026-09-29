import asyncio

from sqlalchemy.orm import Session

from app.core.types import DocumentStatus
from app.main import app, lifespan
from app.models.document import Document
from app.models.user import User


class SessionProxy:
    def __init__(self, session: Session) -> None:
        self.session = session

    def __getattr__(self, name: str):
        return getattr(self.session, name)

    def close(self) -> None:
        pass


def test_startup_cleanup_marks_processing_documents_failed(
    db_session: Session,
    monkeypatch,
) -> None:
    user = User(
        email='startup-cleanup@gmail.com',
        hashed_password='hashed',
    )
    document = Document(
        filename='stale.pdf',
        original_filename='stale.pdf',
        file_path='/tmp/stale.pdf',
        content_type='application/pdf',
        file_size_bytes=123,
        status=DocumentStatus.PROCESSING.value,
    )
    user.documents.append(document)
    db_session.add(user)
    db_session.flush()

    monkeypatch.setattr('app.main.SessionLocal', lambda: SessionProxy(db_session))

    async def run_lifespan() -> None:
        async with lifespan(app):
            pass

    asyncio.run(run_lifespan())

    assert document.status == DocumentStatus.PROCESSING_FAILED.value
    assert document.error_message == (
        'Document processing was interrupted by an application restart. '
        'Please upload the document again.'
    )
