import logging

from app.core.logging import log_event
from app.models.document import Document
from app.services.document_service import DocumentService

logger = logging.getLogger(__name__)


class DocumentQueueUnavailable(Exception):
    pass


def enqueue_document(
    document: Document, service: DocumentService, request_id: str | None
) -> None:
    from app.tasks.document_processing import process_document_task

    try:
        process_document_task.delay(
            str(document.id),
            document.file_path,
            request_id,
            str(document.user_id),
            (
                str(document.processing_attempt_id)
                if document.processing_attempt_id
                else None
            ),
        )
    except Exception as error:
        service.fail_enqueue(document)
        log_event(
            logger,
            logging.ERROR,
            "document.processing.enqueue_failed",
            request_id=request_id,
            user_id=str(document.user_id),
            document_id=str(document.id),
            error_type=type(error).__name__,
        )
        raise DocumentQueueUnavailable(
            "Could not queue document processing. Please retry."
        ) from error
