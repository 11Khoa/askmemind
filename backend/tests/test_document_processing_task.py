import uuid
from pathlib import Path

from app.tasks import document_processing


def test_process_document_task_calls_background_worker(monkeypatch) -> None:
    document_id = uuid.uuid4()
    user_id = uuid.uuid4()
    calls = []

    monkeypatch.setattr(
        document_processing,
        'process_document_in_background',
        lambda **kwargs: calls.append(kwargs),
    )

    result = document_processing.process_document_task.run(
        document_id=str(document_id),
        file_path='/tmp/document.pdf',
        request_id='request-1',
        user_id=str(user_id),
    )

    assert result == {'document_id': str(document_id)}
    assert calls == [
        {
            'document_id': document_id,
            'file_path': Path('/tmp/document.pdf'),
            'request_id': 'request-1',
            'user_id': user_id,
        }
    ]
