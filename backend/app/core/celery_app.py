from celery import Celery

from app.core.config import settings

celery_app = Celery(
    'askmemind',
    broker=settings.resolved_celery_broker_url,
    backend=settings.resolved_celery_result_backend,
    include=['app.tasks.document_processing'],
)

celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,
)
