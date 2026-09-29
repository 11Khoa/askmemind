import uuid
from pathlib import Path

from app.core.celery_app import celery_app
from app.core.dependencies import process_document_in_background


@celery_app.task(name='documents.process')
def process_document_task(
    document_id: str,
    file_path: str,
    request_id: str | None,
    user_id: str,
) -> dict[str, str]:
    process_document_in_background(
        document_id=uuid.UUID(document_id),
        file_path=Path(file_path),
        request_id=request_id,
        user_id=uuid.UUID(user_id),
    )
    return {'document_id': document_id}
