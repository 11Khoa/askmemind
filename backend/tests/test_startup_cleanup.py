import asyncio

from sqlalchemy.orm import Session

from app.core.types import DocumentStatus
from app.main import app, lifespan
from app.models.document import Document
from app.models.user import User


def test_api_restart_does_not_fail_celery_documents(
    db_session: Session,
) -> None:
    user = User(
        email="startup-cleanup@gmail.com",
        hashed_password="hashed",
    )
    document = Document(
        filename="stale.pdf",
        original_filename="stale.pdf",
        file_path="/tmp/stale.pdf",
        content_type="application/pdf",
        file_size_bytes=123,
        status=DocumentStatus.PROCESSING.value,
    )
    user.documents.append(document)
    db_session.add(user)
    db_session.flush()

    async def run_lifespan() -> None:
        async with lifespan(app):
            pass

    asyncio.run(run_lifespan())

    assert document.status == DocumentStatus.PROCESSING.value
    assert document.error_message is None
