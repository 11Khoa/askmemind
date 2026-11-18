"""Durable intent + idempotent worker guards bridge DB and Redis failures."""
import logging
from datetime import UTC, datetime, timedelta
from sqlalchemy import delete, exists, or_, select, update
from app.core.config import settings
from app.core.logging import log_event
from app.models.document_job import DocumentJob
from app.models.document import Document
from app.models.demo_session import DemoSession

logger = logging.getLogger(__name__)


class DocumentQueueUnavailable(Exception):
    pass


def retry_delay():
    return max(settings.document_dispatch_stale_seconds,
               int(settings.pdf_ocr_page_timeout_seconds * 2),
               int(settings.pdf_native_page_timeout_seconds * 2))


def publish(document_id, file_path, user_id, attempt_id, request_id=None):
    from app.tasks.document_processing import process_document_task
    process_document_task.delay(str(document_id), file_path, request_id, str(user_id), str(attempt_id) if attempt_id else None)


def enqueue_document(document, service, request_id):
    # The repository has already committed the intent. Failure here is a queued
    # 202, not a failed document requiring another upload/retry.
    try:
        publish(document.id, document.file_path, document.user_id, document.processing_attempt_id, request_id)
    except Exception as error:
        log_event(logger, logging.WARNING, "document.dispatch.pending", error_type=type(error).__name__)
        return False
    repository = getattr(service, "document_repository", None)
    if repository is not None:
        repository.db.execute(update(DocumentJob).where(
            DocumentJob.document_id == document.id, DocumentJob.attempt_id == document.processing_attempt_id,
        ).values(next_dispatch_at=datetime.now(UTC) + timedelta(seconds=retry_delay()),
                 dispatch_count=DocumentJob.dispatch_count + 1))
        repository.db.commit()
    return True


def dispatch_pending(db, limit=100):
    from app.repositories.document_repository import DocumentRepository
    now = datetime.now(UTC)
    active = exists(select(Document.id).where(Document.id == DocumentJob.document_id,
        Document.status == "processing", Document.processing_attempt_id == DocumentJob.attempt_id))
    db.execute(delete(DocumentJob).where(~active))
    # Release locks before publishing or acquiring a demo session guard.
    rows = db.execute(select(DocumentJob, Document).join(Document, Document.id == DocumentJob.document_id).where(
        DocumentJob.next_dispatch_at <= now,
    ).order_by(DocumentJob.next_dispatch_at).limit(limit).with_for_update(of=DocumentJob, skip_locked=True)).all()
    deliveries = []
    for job, document in rows:
        if document.demo_session_id and db.scalar(select(DemoSession.id).where(
            DemoSession.id == document.demo_session_id, DemoSession.expires_at > now)) is None:
            db.delete(job)
            continue
        # A recent checkpoint is a heartbeat. Never replace a healthy attempt.
        if job.dispatch_count and document.updated_at > now - timedelta(seconds=retry_delay()):
            job.next_dispatch_at = document.updated_at + timedelta(seconds=retry_delay())
            continue
        deliveries.append((document.id, document.file_path, document.user_id, job.attempt_id, job.dispatch_count))
        job.next_dispatch_at = now + timedelta(seconds=retry_delay())
    db.commit()
    for document_id, path, user_id, attempt_id, count in deliveries:
        if count >= settings.document_dispatch_max_attempts:
            DocumentRepository(db).fail_attempt(document_id, attempt_id, "Processing worker did not make progress. Please retry.")
            continue
        try:
            publish(document_id, path, user_id, attempt_id)
            db.execute(update(DocumentJob).where(DocumentJob.document_id == document_id,
                DocumentJob.attempt_id == attempt_id).values(dispatch_count=DocumentJob.dispatch_count + 1))
            db.commit()
        except Exception:
            db.execute(update(DocumentJob).where(DocumentJob.document_id == document_id,
                DocumentJob.attempt_id == attempt_id).values(next_dispatch_at=now + timedelta(seconds=30)))
            db.commit()
            logger.warning("document.dispatch.retry_pending")
    return len(deliveries)
