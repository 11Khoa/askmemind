import uuid
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from app.core import dependencies
from app.main import app
from app.models.document import Document
from app.models.user import User
from app.repositories.document_repository import DocumentRepository
from app.repositories.user_repository import UserRepository
from app.services.document_service import DocumentService
from app.tasks.document_processing import process_document_task


@pytest.fixture
def failed_document(db_session, tmp_path):
    user = User(email=f"retry-{uuid.uuid4()}@example.com", hashed_password="hashed")
    pdf = tmp_path / "retry.pdf"
    pdf.write_bytes(b"%PDF-1.7\n")
    document = Document(
        user=user,
        filename="stored.pdf",
        original_filename="original.pdf",
        file_path=str(pdf),
        content_type="application/pdf",
        file_size_bytes=12,
        status="processing_failed",
        error_message="Previous failure",
        processing_attempt_id=uuid.uuid4(),
    )
    db_session.add(document)
    db_session.flush()
    return document


@pytest.fixture
def retry_client(db_session, failed_document, monkeypatch):
    service = DocumentService(
        DocumentRepository(db_session), UserRepository(db_session)
    )
    app.dependency_overrides[dependencies.get_current_user] = (
        lambda: failed_document.user
    )
    app.dependency_overrides[dependencies.get_document_service] = lambda: service
    queued = Mock()
    monkeypatch.setattr(process_document_task, "delay", queued)
    try:
        with TestClient(app) as client:
            yield client, queued
    finally:
        app.dependency_overrides.clear()


def test_retry_returns_same_document_and_rejects_second_click(
    retry_client, failed_document
):
    client, queued = retry_client
    old_attempt = failed_document.processing_attempt_id
    response = client.post(f"/documents/{failed_document.id}/retry")
    assert response.status_code == 202
    payload = response.json()
    assert payload["id"] == str(failed_document.id)
    assert payload["status"] == "processing"
    assert payload["error_message"] is None
    assert payload["processing_attempt_id"] != str(old_attempt)
    assert queued.call_args.args == (
        str(failed_document.id),
        failed_document.file_path,
        response.headers["X-Request-ID"],
        str(failed_document.user_id),
        payload["processing_attempt_id"],
    )
    assert client.post(f"/documents/{failed_document.id}/retry").status_code == 409
    assert queued.call_count == 1


def test_retry_checks_owner_and_missing_document(retry_client, failed_document):
    client, queued = retry_client
    app.dependency_overrides[dependencies.get_current_user] = lambda: Mock(
        id=uuid.uuid4()
    )
    assert client.post(f"/documents/{failed_document.id}/retry").status_code == 403
    assert client.get(f"/documents/{failed_document.id}").status_code == 403
    assert client.post(f"/documents/{uuid.uuid4()}/retry").status_code == 404
    queued.assert_not_called()


def test_retry_missing_original_explains_reupload(retry_client, failed_document):
    client, queued = retry_client
    Path(failed_document.file_path).unlink()
    response = client.post(f"/documents/{failed_document.id}/retry")
    assert response.status_code == 409
    assert "Upload it again" in response.json()["detail"]
    assert failed_document.status == "processing_failed"
    queued.assert_not_called()


def test_retry_can_resume_checkpoint_without_original(
    retry_client, failed_document, db_session
):
    client, queued = retry_client
    failed_document.chunk_count = 2
    db_session.flush()
    Path(failed_document.file_path).unlink()
    assert client.post(f"/documents/{failed_document.id}/retry").status_code == 202
    queued.assert_called_once()


def test_enqueue_failure_leaves_document_retryable(retry_client, failed_document):
    client, queued = retry_client
    queued.side_effect = RuntimeError("broker unavailable")
    response = client.post(f"/documents/{failed_document.id}/retry")
    assert response.status_code == 503
    assert failed_document.status == "processing_failed"
    assert "Could not queue" in failed_document.error_message
    queued.side_effect = None
    assert client.post(f"/documents/{failed_document.id}/retry").status_code == 202


def test_processing_lock_excludes_concurrent_worker(db_session, failed_document):
    repository = DocumentRepository(db_session)
    with repository.processing_lock(failed_document.id) as first:
        assert first
        db_session.commit()
        with repository.processing_lock(failed_document.id) as duplicate:
            assert not duplicate
    with repository.processing_lock(failed_document.id) as released:
        assert released


class SessionProxy:
    def __init__(self, session):
        self.session = session

    def __getattr__(self, name):
        return getattr(self.session, name)

    def close(self):
        pass


@pytest.mark.parametrize("publish_fails", [False, True])
def test_worker_success_ignores_duplicate_and_sse_failure(
    db_session, failed_document, monkeypatch, publish_fails
):
    document = failed_document
    document.status = "processing"
    db_session.flush()
    service = Mock()

    def complete(**kwargs):
        DocumentRepository(db_session).mark_processing_completed(document, 2)
        db_session.commit()

    service.process_document.side_effect = complete
    publish = Mock(
        side_effect=RuntimeError("redis unavailable") if publish_fails else None
    )
    monkeypatch.setattr(dependencies, "SessionLocal", lambda: SessionProxy(db_session))
    monkeypatch.setattr(
        dependencies, "build_document_processing_service", lambda db: service
    )
    monkeypatch.setattr(dependencies.document_event_broker, "publish", publish)
    args = (
        document.id,
        Path(document.file_path),
        "retry-request",
        document.user_id,
        document.processing_attempt_id,
    )
    dependencies.process_document_in_background(*args)
    dependencies.process_document_in_background(*args)
    assert document.status == "ready"
    assert document.error_message is None
    assert document.page_count == 2
    service.process_document.assert_called_once()
    assert publish.call_args.args[1]["status"] == "ready"


def test_stale_or_busy_task_does_not_process(db_session, failed_document, monkeypatch):
    document = failed_document
    document.status = "processing"
    db_session.flush()
    factory = Mock()
    monkeypatch.setattr(dependencies, "SessionLocal", lambda: SessionProxy(db_session))
    monkeypatch.setattr(dependencies, "build_document_processing_service", factory)
    args = (document.id, Path(document.file_path), None, document.user_id)
    dependencies.process_document_in_background(
        *args, processing_attempt_id=uuid.uuid4()
    )
    monkeypatch.setattr(
        DocumentRepository, "processing_lock", lambda *args: nullcontext(False)
    )
    dependencies.process_document_in_background(
        *args, processing_attempt_id=document.processing_attempt_id
    )
    factory.assert_not_called()


def test_retry_does_not_claim_while_previous_worker_is_finishing(
    retry_client, failed_document, db_session
):
    client, queued = retry_client
    with DocumentRepository(db_session).processing_lock(failed_document.id) as acquired:
        assert acquired
        assert client.post(f"/documents/{failed_document.id}/retry").status_code == 409
    assert failed_document.status == "processing_failed"
    queued.assert_not_called()


def test_two_sessions_cannot_claim_the_same_retry():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from app.database import SessionLocal

    with SessionLocal() as db:
        user = User(
            email=f"retry-race-{uuid.uuid4()}@example.com", hashed_password="hashed"
        )
        document = Document(
            user=user,
            filename="race.pdf",
            original_filename="race.pdf",
            file_path="/tmp/race.pdf",
            content_type="application/pdf",
            file_size_bytes=12,
            status="processing_failed",
        )
        db.add(document)
        db.commit()
        user_id, document_id = user.id, document.id
    barrier = Barrier(2)

    def claim():
        with SessionLocal() as db:
            barrier.wait(timeout=10)
            result = DocumentRepository(db).claim_retry(document_id, user_id)
            return str(result.processing_attempt_id) if result else None

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: claim(), range(2)))
        assert sum(result is not None for result in results) == 1
    finally:
        with SessionLocal() as db:
            db.delete(db.get(User, user_id))
            db.commit()


def test_upload_enqueue_failure_keeps_file_and_a_retryable_row(
    retry_client, failed_document
):
    client, queued = retry_client
    queued.side_effect = RuntimeError("broker unavailable")
    storage = Mock()
    storage.save_upload.return_value = failed_document.file_path
    app.dependency_overrides[dependencies.get_file_storage_service] = lambda: storage
    response = client.post(
        "/documents/upload",
        files={"file": ("new.pdf", b"%PDF-1.7\n", "application/pdf")},
    )
    assert response.status_code == 503
    documents = client.get("/documents").json()
    uploaded = next(
        document for document in documents if document["original_filename"] == "new.pdf"
    )
    assert uploaded["status"] == "processing_failed"
    assert "Could not queue" in uploaded["error_message"]
    storage.delete_file.assert_not_called()


def test_cancel_is_idempotent_and_retains_a_resumable_document(retry_client, failed_document, db_session):
    client, queued = retry_client
    failed_document.status = "processing"
    failed_document.processing_progress = {"stage": "ocr", "completed_pages": 12,
        "total_pages": 144, "started_at": "2026-10-27T00:00:00+00:00"}
    db_session.commit()
    response = client.post(f"/documents/{failed_document.id}/cancel")
    assert response.status_code == 200
    row = response.json()
    assert row["status"] == "cancelled" and row["processing_attempt_id"] is None
    assert row["processing_progress"]["completed_pages"] == 12
    assert row["processing_progress"]["finished_at"]
    assert row["processing_progress"]["started_at"] == "2026-10-27T00:00:00+00:00"
    assert Path(failed_document.file_path).exists()
    queued.assert_not_called()
    again = client.post(f"/documents/{failed_document.id}/cancel")
    assert again.json()["processing_progress"]["finished_at"] == row["processing_progress"]["finished_at"]
    resumed = client.post(f"/documents/{failed_document.id}/retry")
    assert resumed.status_code == 202
    assert resumed.json()["status"] == "processing"
    assert resumed.json()["processing_attempt_id"]
    assert resumed.json()["processing_progress"]["started_at"] is None
    queued.assert_called_once()


def test_cancel_cannot_modify_a_finished_document(retry_client, failed_document, db_session):
    client, _ = retry_client
    failed_document.status = "ready"
    db_session.commit()
    assert client.post(f"/documents/{failed_document.id}/cancel").status_code == 409
    assert db_session.get(Document, failed_document.id).status == "ready"


def test_other_user_cannot_cancel_document(retry_client, failed_document, db_session):
    client, _ = retry_client
    failed_document.status = "processing"
    other = User(email=f"other-{uuid.uuid4()}@example.com", hashed_password="hash")
    db_session.add(other)
    db_session.commit()
    app.dependency_overrides[dependencies.get_current_user] = lambda: other
    assert client.post(f"/documents/{failed_document.id}/cancel").status_code == 403
    assert db_session.get(Document, failed_document.id).status == "processing"
