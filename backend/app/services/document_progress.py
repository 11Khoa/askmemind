"""Committed page checkpoints and best-effort progress events, scoped to an attempt."""
import logging
from time import monotonic

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert

from app.models.document import Document
from app.models.document_page_checkpoint import DocumentPageCheckpoint
from app.services.document_events import document_event_broker

logger = logging.getLogger(__name__)


def processing_error_code(message: str, stage: str | None = None) -> str:
    text = message.lower()
    if "timeout" in text and stage in {"ocr", "extracting"}:
        return "ocr_timeout"
    if "ocr page limit" in text:
        return "ocr_page_limit"
    if "models unavailable" in text or "checksum" in text or "vocabulary" in text:
        return "ocr_models"
    if "extractable text" in text:
        return "no_text"
    if "original pdf is unavailable" in text:
        return "file_missing"
    if stage == "embedding":
        return "embedding_failed"
    return "processing_failed"


def failed_progress(progress: dict | None, message: str) -> dict:
    previous = progress or {}
    stage = previous.get("stage")
    return {**previous, "stage": "failed", "failed_stage": stage,
            "error_code": processing_error_code(message, stage)}


class DocumentProgress:
    def __init__(self, repository, document):
        self.db = repository.db
        self.document = document
        self.attempt_id = document.processing_attempt_id
        self._events_available = True
        self._last_event = 0.0
        self._last_stage = None

    def _condition(self):
        return (Document.id == self.document.id,
                Document.processing_attempt_id == self.attempt_id,
                Document.status == "processing")

    def _check_attempt(self):
        if self.db.scalar(select(Document.id).where(*self._condition()).with_for_update()) is None:
            raise ValueError("Document processing attempt is no longer active")

    def begin(self, fingerprint: str, total: int) -> dict:
        self._check_attempt()
        self.db.execute(delete(DocumentPageCheckpoint).where(
            DocumentPageCheckpoint.document_id == self.document.id,
            DocumentPageCheckpoint.fingerprint != fingerprint,
        ))
        rows = self.db.scalars(select(DocumentPageCheckpoint).where(
            DocumentPageCheckpoint.document_id == self.document.id,
            DocumentPageCheckpoint.fingerprint == fingerprint,
        )).all()
        self.fingerprint = fingerprint
        self.db.commit()
        self.report(stage="extracting", completed_pages=0, total_pages=total,
                    current_page=None, reused_pages=0, error_code=None, failed_stage=None)
        return {row.page_number: {"text": row.content, "metadata": row.extraction_metadata} for row in rows}

    def save(self, page_number: int, text: str, metadata: dict):
        self._check_attempt()
        statement = insert(DocumentPageCheckpoint).values(
            document_id=self.document.id, page_number=page_number,
            fingerprint=self.fingerprint, content=text, extraction_metadata=metadata,
        )
        self.db.execute(statement.on_conflict_do_update(
            index_elements=["document_id", "page_number"],
            set_={"fingerprint": self.fingerprint, "content": text, "extraction_metadata": metadata},
        ))
        self.db.commit()

    def report(self, **values):
        progress = {**(self.document.processing_progress or {}), **values}
        result = self.db.execute(update(Document).where(*self._condition()).values(
            processing_progress=progress, updated_at=func.clock_timestamp(),
        ).returning(Document.updated_at))
        updated_at = result.scalar_one_or_none()
        if updated_at is None:
            self.db.rollback()
            raise ValueError("Document processing attempt is no longer active")
        self.db.commit()
        # ORM synchronize_session updates document.processing_progress too.
        if not self._events_available:
            return
        now = monotonic()
        if progress.get("stage") == self._last_stage and now - self._last_event < 1:
            return
        self._last_event, self._last_stage = now, progress.get("stage")
        try:
            document_event_broker.publish(self.document.user_id, {
                "document_id": str(self.document.id), "status": "processing",
                "processing_attempt_id": str(self.attempt_id) if self.attempt_id else None,
                "processing_progress": progress, "page_count": self.document.page_count,
                "error_message": None, "updated_at": updated_at.isoformat(),
            })
        except Exception:
            self._events_available = False
            logger.warning("document.progress.event_failed")
