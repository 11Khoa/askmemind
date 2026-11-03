"""Real HTTP/database isolation with two independent cookie jars, one shared account."""
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select, func
from app.main import app
from app.core.config import settings
from app.core.security import hash_password
from app.core.data_scope import DataScope
from app.models.user import User
from app.models.demo_session import DemoSession
from app.models.document import Document
from app.models.chunk import Chunk
from app.models.chat import Chat
from app.models.chat_message import ChatMessage
from app.models.audit_event import AuditEvent
from app.services import demo_service
from app.services.document_progress import DocumentProgress, ProcessingStopped
from app.repositories.document_repository import DocumentRepository
from app.repositories.chunk_repository import ChunkRepository
from app.repositories.chat_repository import ChatRepository


@pytest.fixture
def demo(db_session, browser_client, monkeypatch, tmp_path):
    user = User(email=f"demo-{uuid.uuid4()}@example.com", hashed_password=hash_password("demo-password"), is_demo=True)
    normal = User(email=f"normal-{uuid.uuid4()}@example.com", hashed_password=hash_password("normal-password"))
    admin = User(email=f"admin-{uuid.uuid4()}@example.com", hashed_password=hash_password("admin-password"), role="admin")
    db_session.add_all([user, normal, admin]); db_session.commit()
    from app.core.dependencies import get_file_storage_service
    from app.services.file_storage_service import FileStorageService
    app.dependency_overrides[get_file_storage_service] = lambda: FileStorageService(str(tmp_path))
    monkeypatch.setattr("app.routers.upload.enqueue_document", lambda *args: None)
    clients = []
    def login(account=user, password="demo-password"):
        client = TestClient(app, base_url="https://api.example.com", headers={"Origin": "https://app.example.com", "X-CSRF-Protection": "1"})
        response = client.post('/auth/login', json={"email": account.email, "password": password})
        assert response.status_code == 200, response.text
        client.headers['Authorization'] = f"Bearer {response.json()['access_token']}"
        clients.append(client)
        return client
    yield user, normal, admin, login
    for client in clients:
        client.close()
    app.dependency_overrides.pop(get_file_storage_service, None)


def upload(client, filename='private.pdf'):
    return client.post('/documents/upload', files={'file': (filename, b'%PDF-1.4\n demo', 'application/pdf')})


def accept(client):
    response = client.post('/demo/notice/accept', json={'notice_version': settings.demo_notice_version})
    assert response.status_code == 200, response.text
    return response


def test_two_browsers_share_account_but_self_delete_only_removes_a(demo, db_session):
    user, normal, admin, login = demo
    a, b = login(), login()
    old_cookie = a.cookies.get(demo_service.COOKIE)
    assert old_cookie != b.cookies.get(demo_service.COOKIE)
    accept(a); accept(b)
    da, db = upload(a).json(), upload(b).json()
    ca, cb = a.post('/chats', json={'title': 'A'}).json(), b.post('/chats', json={'title': 'B'}).json()
    assert a.post(f"/chats/{ca['id']}/messages", json={'content': 'A secret'}).status_code == 200
    assert b.post(f"/chats/{cb['id']}/messages", json={'content': 'B secret'}).status_code == 200
    scope_a=DataScope(user.id,uuid.UUID(a.cookies.get(demo_service.COOKIE).split('.')[0]))
    assert ChatRepository(db_session,scope_a).list_messages_by_chat(uuid.UUID(cb['id']))==[]
    assert [d['id'] for d in a.get('/documents').json()] == [da['id']]
    assert [d['id'] for d in b.get('/documents').json()] == [db['id']]
    assert [c['id'] for c in a.get('/chats').json()] == [ca['id']]
    for endpoint in (f"/documents/{db['id']}", f"/documents/{db['id']}/file", f"/documents/{db['id']}/chunks/{uuid.uuid4()}", f"/chats/{cb['id']}/messages"):
        assert a.get(endpoint).status_code == 404
    assert a.post(f"/documents/{db['id']}/cancel").status_code == 404
    assert a.post(f"/documents/{db['id']}/retry").status_code == 404
    assert a.delete('/demo/session').json()['deleted']
    assert demo_service.COOKIE not in a.cookies
    assert db_session.get(Document, uuid.UUID(da['id'])) is None
    assert db_session.get(Chat, uuid.UUID(ca['id'])) is None
    assert not Path(da['file_path']).exists()
    assert Path(db['file_path']).exists()
    assert b.get(f"/chats/{cb['id']}/messages").json()[0]['content'] == 'B secret'
    assert b.get(f"/documents/{db['id']}").status_code == 200
    assert a.get('/documents', headers={'Cookie': f'{demo_service.COOKIE}={old_cookie}'}).status_code == 410
    assert a.post('/demo/bootstrap').status_code == 200
    assert a.get('/documents').json() == []
    assert a.get('/demo/status').json()['notice_accepted'] is False
    assert db_session.get(User, user.id) is not None


def test_normal_user_has_no_demo_session_or_notice(demo, db_session):
    _, normal, _, login = demo
    client = login(normal, 'normal-password')
    assert demo_service.COOKIE not in client.cookies
    assert client.get('/demo/status').json()['is_demo'] is False
    assert upload(client).status_code == 202
    assert client.post('/chats', json={'title':'normal'}).status_code == 200
    assert client.delete('/demo/session').status_code == 403
    assert db_session.scalar(select(func.count()).select_from(DemoSession)) == 0


def test_notice_upload_toggle_expiry_and_version(demo, db_session, monkeypatch):
    user, _, _, login = demo
    client = login()
    assert upload(client).status_code == 428
    assert client.post('/chats', json={'title':'blocked'}).status_code == 428
    accept(client)
    assert upload(client).status_code == 202
    chat = client.post('/chats', json={'title':'ok'}).json()
    monkeypatch.setattr(settings, 'demo_notice_version', 'v2')
    assert client.post(f"/chats/{chat['id']}/messages", json={'content':'blocked'}).status_code == 428
    assert client.get('/demo/status').json()['notice_accepted'] is False
    accept(client)
    user.demo_upload_enabled = False; db_session.commit()
    assert upload(client).status_code == 403
    session = db_session.scalar(select(DemoSession).where(DemoSession.user_id == user.id))
    session.expires_at = datetime.now(UTC) - timedelta(seconds=1); db_session.commit()
    assert upload(client).status_code == 410
    assert client.post(f"/chats/{chat['id']}/messages", json={'content':'blocked'}).status_code == 410
    assert client.get('/documents').status_code == 410
    # Expired owner can still explicitly finish its cleanup.
    assert client.delete('/demo/session').status_code == 200


def test_forged_session_ids_and_admin_only_operations(demo, db_session):
    user, normal, admin, login = demo
    client = login(); accept(client)
    assert client.patch(f'/admin/users/{user.id}/demo-config', json={'is_demo': False, 'demo_retention_minutes':60, 'demo_upload_enabled':True}).status_code == 403
    assert client.delete(f'/admin/users/{user.id}/demo-data').status_code == 403
    assert client.delete(f'/demo/session/{uuid.uuid4()}').status_code == 404
    # Query/body identifiers cannot select a different session.
    other = login(); accept(other)
    original_other = other.cookies.get(demo_service.COOKIE)
    assert client.delete(f'/demo/session?demo_session_id={original_other}').status_code == 200
    assert other.get('/demo/status').status_code == 200
    client.cookies.clear(); client.cookies.set(demo_service.COOKIE, str(uuid.uuid4()))
    assert client.get('/documents').status_code == 410
    normal_client = login(normal, 'normal-password')
    normal_client.cookies.set(demo_service.COOKIE, original_other)
    assert normal_client.get('/documents').json() == []


def test_csrf_and_cookie_flags(demo):
    *_, login = demo
    client = login()
    assert client.cookies.get(demo_service.COOKIE)
    client.headers.pop('X-CSRF-Protection')
    assert client.delete('/demo/session').status_code == 403
    assert client.post('/demo/notice/accept').status_code == 403
    client.headers['X-CSRF-Protection'] = '1'
    client.headers['Origin'] = 'https://evil.example'
    assert client.delete('/demo/session').status_code == 403


def test_cleanup_is_idempotent_and_preserves_normal_data(demo, db_session):
    user, normal, _, login = demo
    a = login(); accept(a); document = upload(a).json()
    n = login(normal, 'normal-password'); normal_doc = upload(n).json()
    document_id = uuid.UUID(document['id'])
    db_session.add(Chunk(document_id=document_id,chunk_index=0,content='private chunk',embedding_v2=[0.1]*2048))
    db_session.commit()
    identifier = uuid.UUID(a.cookies.get(demo_service.COOKIE).split('.')[0])
    session = db_session.get(DemoSession, identifier)
    session.expires_at = datetime.now(UTC) - timedelta(seconds=1); db_session.commit()
    from app.tasks.demo_cleanup import cleanup_expired_demo_sessions
    from contextlib import nullcontext
    from unittest.mock import patch
    with patch('app.tasks.demo_cleanup.SessionLocal', lambda: nullcontext(db_session)):
        cleanup_expired_demo_sessions.run()
        cleanup_expired_demo_sessions.run()
    assert not Path(document['file_path']).exists()
    assert db_session.get(Document, uuid.UUID(document['id'])) is None
    assert db_session.query(Chunk).filter(Chunk.document_id==document_id).count()==0
    assert db_session.get(Document, uuid.UUID(normal_doc['id'])) is not None
    assert Path(normal_doc['file_path']).exists()
    assert demo_service.cleanup_session(db_session, identifier) is False


def test_admin_config_validation_cleanup_and_safe_mode_transition(demo, db_session):
    user, normal, admin, login = demo
    a, b = login(), login(); accept(a); accept(b)
    upload(a); upload(b)
    root = login(admin, 'admin-password')
    path = f'/admin/users/{user.id}/demo-config'
    payload = {'is_demo':True, 'demo_retention_minutes':30, 'demo_upload_enabled':False}
    assert root.patch(path, json={**payload, 'demo_retention_minutes':1}).status_code == 422
    assert root.patch(path, json=payload).status_code == 200
    assert upload(a).status_code == 403
    # Existing sessions retain the lifetime actually accepted, not a new rolling timer.
    assert a.get('/demo/status').json()['retention_minutes'] == 60
    assert root.patch(path, json={**payload,'is_demo':False}).status_code == 409
    assert root.delete(f'/admin/users/{user.id}/demo-data').json()['sessions_deleted'] == 2
    assert a.get('/documents').status_code == 410
    assert root.patch(path, json={**payload,'is_demo':False}).status_code == 200
    assert a.get('/documents').status_code == 401
    assert db_session.query(AuditEvent).filter(AuditEvent.action == 'admin.demo.config.update').count() >= 2


def test_worker_and_chat_persistence_stop_after_expiry_or_cleanup(demo, db_session):
    user, _, _, login = demo
    client = login(); accept(client)
    data = upload(client).json()
    document = db_session.get(Document, uuid.UUID(data['id']))
    progress = DocumentProgress(DocumentRepository(db_session), document)
    progress.start()
    session_id = document.demo_session_id
    chat = ChatRepository(db_session, DataScope(user.id, session_id)).create_chat(user.id, 'private')
    repo = ChatRepository(db_session, DataScope(user.id, session_id))
    chat_id = chat.id
    session = db_session.get(DemoSession, session_id)
    session.expires_at = datetime.now(UTC) - timedelta(seconds=1); db_session.commit()
    with pytest.raises(ProcessingStopped): progress.guard_writes()
    db_session.rollback()
    with pytest.raises(HTTPException): repo.create_message(chat_id, 0, 'assistant', 'late')
    db_session.rollback()
    demo_service.cleanup_session(db_session, session_id)
    with pytest.raises(ProcessingStopped): progress.guard_writes()
    db_session.rollback()
    assert db_session.query(Chunk).count() == 0
    assert db_session.query(ChatMessage).count() == 0


def test_retrieval_scope_and_legacy_data_never_bleed(demo, db_session):
    user, _, _, login = demo
    a,b = login(),login(); accept(a);accept(b)
    da,db = upload(a).json(),upload(b).json()
    docs = [db_session.get(Document, uuid.UUID(data['id'])) for data in (da,db)]
    for index,doc in enumerate(docs):
        doc.status='ready'
        db_session.add(Chunk(document_id=doc.id,chunk_index=0,content=f'keyword private {index}',embedding_v2=[0.1]*2048))
    legacy=Document(user_id=user.id,filename='legacy.pdf',original_filename='legacy.pdf',file_path='/missing',content_type='application/pdf',file_size_bytes=10,status='ready')
    db_session.add(legacy);db_session.flush()
    db_session.add(Chunk(document_id=legacy.id,chunk_index=0,content='keyword legacy',embedding_v2=[0.1]*2048))
    db_session.commit()
    scope = DataScope(user.id, uuid.UUID(a.cookies.get(demo_service.COOKIE).split('.')[0]))
    rows = ChunkRepository(db_session, scope).search_keyword_chunks('keyword', user.id)
    assert [chunk.document_id for chunk,_ in rows] == [docs[0].id]
    scoped_chunks=ChunkRepository(db_session,scope)
    assert scoped_chunks.list_chunks_by_document(docs[1].id)==[]
    vectors=scoped_chunks.search_similar_chunks([0.1]*2048,user.id,use_v2=True)
    assert [chunk.document_id for chunk,_ in vectors]==[docs[0].id]
    chunk_b = db_session.scalar(select(Chunk).where(Chunk.document_id == docs[1].id))
    assert a.get(f'/documents/{docs[1].id}/chunks/{chunk_b.id}').status_code == 404
    assert a.post('/chats', json={'title':'query'}).status_code == 200
    chat=a.get('/chats').json()[0]
    assert a.post(f"/chats/{chat['id']}/questions", json={'content':'keyword', 'document_id':str(docs[1].id)}).status_code == 404
    assert len(a.get('/documents').json())==1


def test_file_quota_is_per_session_and_size_is_bounded(demo, monkeypatch):
    *_, login = demo
    a,b=login(),login(); accept(a);accept(b)
    monkeypatch.setattr(settings, 'demo_max_files', 1)
    monkeypatch.setattr(settings, 'demo_max_upload_size_mb', 1)
    assert upload(a).status_code == 202
    assert upload(a).status_code == 409
    assert upload(b).status_code == 202
    assert b.post('/documents/upload', files={'file':('huge.pdf', b'%PDF-' + b'x' * (1024*1024), 'application/pdf')}).status_code == 413
    assert b.post('/demo/notice/accept', json={'notice_version':'outdated'}).status_code == 428


def test_missing_pdf_and_failed_file_cleanup_are_retryable(demo, db_session, monkeypatch):
    *_, login=demo
    client=login();accept(client)
    document=upload(client).json(); identifier=uuid.UUID(client.cookies.get(demo_service.COOKIE).split('.')[0])
    original=Path.unlink
    def fail(path, *args, **kwargs):
        if str(path)==document['file_path']: raise PermissionError('unavailable')
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'unlink',fail)
    assert client.delete('/demo/session').status_code==503
    assert client.get('/documents').status_code==410
    assert db_session.get(DemoSession,identifier) is not None
    monkeypatch.setattr(Path,'unlink',original)
    Path(document['file_path']).unlink()
    assert client.delete('/demo/session').status_code==200
    assert demo_service.cleanup_session(db_session,identifier) is False


def test_late_embedding_result_cannot_restore_deleted_session(demo, db_session):
    user,_,_,login=demo
    client=login();accept(client)
    data=upload(client).json(); document=db_session.get(Document,uuid.UUID(data['id']))
    document.chunk_count=1
    db_session.add(Chunk(document_id=document.id,chunk_index=0,content='text already extracted'))
    db_session.commit()
    from app.services.document_processing_service import DocumentProcessingService
    from app.services.chunk_persistence_service import ChunkPersistenceService
    embeddings=Mock(embedding_provider='test',embedding_model='model',embedding_dimensions=2048)
    identifier=document.demo_session_id
    def provider(**kwargs):
        demo_service.cleanup_session(db_session,identifier)
        return [[0.1]*2048]
    embeddings.embed_passages.side_effect=provider
    repository=DocumentRepository(db_session)
    service=DocumentProcessingService(Mock(),Mock(),embeddings,ChunkPersistenceService(ChunkRepository(db_session)),repository,db_session,
        checkpoint_factory=lambda doc: DocumentProgress(repository,doc))
    with pytest.raises(ProcessingStopped):
        service.process_document(document.id,Path(data['file_path']))
    assert db_session.query(Chunk).count()==0
    assert db_session.get(Document,uuid.UUID(data['id'])) is None


def test_cookie_is_httponly_secure_host_only_and_no_session_id_returned(demo):
    user,_,_,login=demo
    client=login()
    cookie=next(cookie for cookie in client.cookies.jar if cookie.name==demo_service.COOKIE)
    assert cookie.secure and cookie.path=='/' and not cookie.domain_specified
    assert cookie.has_nonstandard_attr('HttpOnly')
    assert cookie.get_nonstandard_attr('SameSite')=='lax'
    data=client.get('/demo/status').json()
    assert 'id' not in data and 'demo_session_id' not in data


def test_demo_sse_never_publishes_on_shared_account_channel(monkeypatch):
    from app.services.document_events import DocumentEventBroker
    import redis
    client=Mock();monkeypatch.setattr(redis.Redis,'from_url',Mock(return_value=client))
    user,session=uuid.uuid4(),uuid.uuid4()
    broker=DocumentEventBroker('redis://unused')
    broker.publish(user,{'document_id':'private','status':'ready'},demo_session_id=session)
    assert client.publish.call_args_list[0].args[0]==f'document-events:{user}:demo:{session}'
    assert all(call.args[0]!=f'document-events:{user}' for call in client.publish.call_args_list)


def test_cleanup_from_second_connection_wins_over_inflight_embedding(tmp_path):
    """Exercise actual transaction visibility, not a mocked or same-session delete."""
    import threading
    from concurrent.futures import ThreadPoolExecutor
    from app.database import SessionLocal
    from app.services.document_processing_service import DocumentProcessingService
    from app.services.chunk_persistence_service import ChunkPersistenceService
    started, resume = threading.Event(), threading.Event()
    path=tmp_path/'concurrent.pdf';path.write_bytes(b'%PDF-1.4')
    with SessionLocal() as db:
        user=User(email=f'concurrent-{uuid.uuid4()}@example.com',hashed_password='hash',is_demo=True)
        db.add(user);db.flush();user_id=user.id
        session=DemoSession(user_id=user.id,created_at=datetime.now(UTC),expires_at=datetime.now(UTC)+timedelta(hours=1))
        db.add(session);db.flush();session_id=session.id
        document=Document(user_id=user.id,demo_session_id=session.id,filename='concurrent.pdf',original_filename='concurrent.pdf',file_path=str(path),content_type='application/pdf',file_size_bytes=10,status='processing',processing_attempt_id=uuid.uuid4(),chunk_count=1)
        db.add(document);db.flush();document_id=document.id
        db.add(Chunk(document_id=document.id,chunk_index=0,content='private demo text'))
        db.commit()
    def worker():
        with SessionLocal() as db:
            repository=DocumentRepository(db)
            embeddings=Mock(embedding_provider='test',embedding_model='model',embedding_dimensions=2048)
            def provider(**kwargs):
                started.set()
                assert resume.wait(10), 'cleanup did not complete while provider was in flight'
                return [[0.1]*2048]
            embeddings.embed_passages.side_effect=provider
            service=DocumentProcessingService(Mock(),Mock(),embeddings,ChunkPersistenceService(ChunkRepository(db)),repository,db,
                checkpoint_factory=lambda doc:DocumentProgress(repository,doc))
            service.process_document(document_id,path)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(worker)
            assert started.wait(10)
            with SessionLocal() as db:
                assert demo_service.cleanup_session(db,session_id)
            resume.set()
            with pytest.raises(ProcessingStopped):future.result(timeout=10)
        with SessionLocal() as db:
            assert db.get(Document,document_id) is None
            assert db.query(Chunk).filter(Chunk.document_id==document_id).count()==0
        assert not path.exists()
    finally:
        resume.set()
        with SessionLocal() as db:
            db.query(User).filter(User.id==user_id).delete()
            db.commit()


def test_valid_session_cookie_from_another_demo_account_is_rejected(demo, db_session):
    user,other,_,login=demo
    a=login();accept(a)
    other.is_demo=True;db_session.commit()
    b=login(other,'normal-password')
    assert b.get('/documents',headers={'Cookie':f'{demo_service.COOKIE}={a.cookies.get(demo_service.COOKIE)}'}).status_code==410


def test_existing_normal_data_stays_outside_new_demo_sessions(demo, db_session):
    _,normal,admin,login=demo
    client=login(normal,'normal-password')
    old=upload(client).json()
    root=login(admin,'admin-password')
    payload={'is_demo':True,'demo_retention_minutes':60,'demo_upload_enabled':True}
    assert root.patch(f'/admin/users/{normal.id}/demo-config',json=payload).status_code==200
    assert client.get('/documents').status_code==401
    demo_client=login(normal,'normal-password')
    assert demo_client.get('/documents').json()==[]
    assert demo_client.get(f"/documents/{old['id']}").status_code==404
    assert db_session.get(Document,uuid.UUID(old['id'])) is not None


def test_admin_can_delete_one_session_without_deleting_others(demo):
    user,_,admin,login=demo
    a,b=login(),login();accept(a);accept(b)
    root=login(admin,'admin-password')
    items=root.get(f'/admin/users/{user.id}/demo-sessions').json()['items']
    assert len(items)==2
    identifier=a.cookies.get(demo_service.COOKIE).split('.')[0]
    endpoint=f'/admin/users/{user.id}/demo-sessions/{identifier}'
    assert b.delete(endpoint).status_code==403
    assert root.delete(endpoint).status_code==200
    assert a.get('/documents').status_code==410
    assert b.get('/documents').status_code==200


def test_demo_questions_have_session_and_account_limits(demo):
    user,_,_,login=demo
    client=login()
    from app.core.rate_limits import limit_questions
    store=Mock();store.allow_request.return_value=True
    session_id=uuid.UUID(client.cookies.get(demo_service.COOKIE).split('.')[0])
    limit_questions(user,store,DataScope(user.id,session_id))
    assert store.allow_request.call_args_list[0].args==(f'demo:questions:{session_id}',settings.demo_questions_per_minute,60)
    assert store.allow_request.call_args_list[1].args==(f'questions:user:{user.id}',settings.question_requests_per_minute,60)


def test_real_redis_demo_event_isolation():
    import os, json, redis
    from app.services.document_events import DocumentEventBroker
    url=os.getenv('AUTH_TEST_REDIS_URL')
    if not url:pytest.skip('Requires isolated test Redis')
    broker=DocumentEventBroker(url)
    user,a,b=uuid.uuid4(),uuid.uuid4(),uuid.uuid4()
    with redis.Redis.from_url(url) as client,client.pubsub() as first,client.pubsub() as second,client.pubsub() as shared:
        first.subscribe(f'document-events:{user}:demo:{a}')
        second.subscribe(f'document-events:{user}:demo:{b}')
        shared.subscribe(f'document-events:{user}')
        for subscription in (first,second,shared):assert subscription.get_message(timeout=2)['type']=='subscribe'
        broker.publish(user,{'document_id':'private-a','status':'ready'},demo_session_id=a)
        assert json.loads(first.get_message(ignore_subscribe_messages=True,timeout=2)['data'])['document_id']=='private-a'
        assert second.get_message(ignore_subscribe_messages=True,timeout=.1) is None
        assert shared.get_message(ignore_subscribe_messages=True,timeout=.1) is None


def test_bootstrap_and_accept_do_not_extend_session(demo):
    *_,login=demo
    client=login()
    expiry=client.get('/demo/status').json()['expires_at']
    assert client.post('/demo/bootstrap').json()['expires_at']==expiry
    assert accept(client).json()['expires_at']==expiry


def test_known_other_session_uuid_cannot_be_used_with_forged_signature(demo):
    *_,login=demo
    a,b=login(),login()
    a_signature=a.cookies.get(demo_service.COOKIE).split('.')[1]
    b_identifier=b.cookies.get(demo_service.COOKIE).split('.')[0]
    forged=f'{b_identifier}.{a_signature}'
    assert a.get('/documents',headers={'Cookie':f'{demo_service.COOKIE}={forged}'}).status_code==410
    assert a.get('/documents',headers={'Cookie':f'{demo_service.COOKIE}={b_identifier}'}).status_code==410
