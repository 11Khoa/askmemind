from datetime import UTC, datetime, timedelta
from pathlib import Path
import uuid
from unittest.mock import Mock
import pytest
from app.core.config import settings
from app.core.types import DocumentStatus
from app.models.user import User
from app.models.document_job import DocumentJob
from app.repositories.document_repository import DocumentRepository
from app.services.document_jobs import dispatch_pending, enqueue_document


@pytest.fixture
def queued_document(db_session,tmp_path):
    user=User(email=f'outbox-{uuid.uuid4()}@example.com',hashed_password='hash')
    db_session.add(user);db_session.commit()
    path=tmp_path/'stored.pdf';path.write_bytes(b'%PDF-1.4')
    document=DocumentRepository(db_session).create_document(user.id,'stored.pdf','input.pdf',str(path),'application/pdf',10,DocumentStatus.PROCESSING,'pdf')
    return document


def test_document_and_dispatch_intent_commit_together(db_session,queued_document):
    doc=queued_document
    assert db_session.get(DocumentJob,(doc.id,doc.processing_attempt_id)) is not None


def test_crash_before_enqueue_is_recovered(db_session,queued_document,monkeypatch):
    publish=Mock();monkeypatch.setattr('app.services.document_jobs.publish',publish)
    assert dispatch_pending(db_session)==1
    publish.assert_called_once()
    assert publish.call_args.args[0]==queued_document.id


def test_broker_outage_keeps_pending_intent_without_exhausting_delivery_budget(db_session,queued_document,monkeypatch):
    monkeypatch.setattr('app.services.document_jobs.publish',Mock(side_effect=OSError('unavailable')))
    assert dispatch_pending(db_session)==1
    job=db_session.get(DocumentJob,(queued_document.id,queued_document.processing_attempt_id))
    assert job.dispatch_count==0
    assert queued_document.status=='processing'
    job.next_dispatch_at=datetime.now(UTC)-timedelta(seconds=1);db_session.commit()
    publish=Mock();monkeypatch.setattr('app.services.document_jobs.publish',publish)
    assert dispatch_pending(db_session)==1
    assert job.dispatch_count==1


def test_fresh_progress_is_not_redispatched_and_closed_attempts_are_purged(db_session,queued_document,monkeypatch):
    doc=queued_document
    job=db_session.get(DocumentJob,(doc.id,doc.processing_attempt_id));job.dispatch_count=1
    db_session.commit()
    publish=Mock();monkeypatch.setattr('app.services.document_jobs.publish',publish)
    assert dispatch_pending(db_session)==0
    publish.assert_not_called()
    doc.status='cancelled';db_session.commit()
    dispatch_pending(db_session)
    assert db_session.query(DocumentJob).count()==0


def test_stale_delivery_resumes_but_does_not_loop_forever(db_session,queued_document,monkeypatch):
    doc=queued_document
    doc.updated_at=datetime.now(UTC)-timedelta(days=1)
    job=db_session.get(DocumentJob,(doc.id,doc.processing_attempt_id))
    job.dispatch_count=settings.document_dispatch_max_attempts
    db_session.commit()
    publish=Mock();monkeypatch.setattr('app.services.document_jobs.publish',publish)
    dispatch_pending(db_session)
    publish.assert_not_called()
    assert doc.status=='processing_failed'


def test_cleanup_removes_dispatch_intent(db_session,queued_document):
    doc=queued_document;key=(doc.id,doc.processing_attempt_id)
    db_session.delete(doc);db_session.commit()
    assert db_session.get(DocumentJob,key) is None


def test_lost_commit_acknowledgment_never_deletes_a_committed_pdf(db_session,tmp_path):
    from fastapi.testclient import TestClient
    from sqlalchemy.exc import OperationalError
    from app.main import app
    from app.core.dependencies import get_current_user,get_document_service,get_file_storage_service
    from app.services.document_service import DocumentService
    from app.services.file_storage_service import FileStorageService
    from app.repositories.user_repository import UserRepository
    from app.models.document import Document
    user=User(email=f'commit-{uuid.uuid4()}@example.com',hashed_password='hash')
    db_session.add(user);db_session.commit()
    class LostAcknowledgment:
        def __getattr__(self,name):return getattr(db_session,name)
        def commit(self):
            db_session.commit()
            raise OperationalError('COMMIT',{},Exception('acknowledgment lost'))
    app.dependency_overrides[get_current_user]=lambda:user
    app.dependency_overrides[get_document_service]=lambda:DocumentService(DocumentRepository(LostAcknowledgment()),UserRepository(db_session))
    app.dependency_overrides[get_file_storage_service]=lambda:FileStorageService(str(tmp_path))
    try:
        response=TestClient(app).post('/documents/upload',files={'file':('accepted.pdf',b'%PDF-1.4','application/pdf')})
        assert response.status_code==500
        document=db_session.query(Document).filter(Document.user_id==user.id).one()
        assert Path(document.file_path).is_file()
        assert db_session.get(DocumentJob,(document.id,document.processing_attempt_id)) is not None
    finally:
        for dep in (get_current_user,get_document_service,get_file_storage_service):app.dependency_overrides.pop(dep,None)
