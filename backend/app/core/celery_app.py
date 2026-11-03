from celery import Celery

from app.core.config import settings

celery_app = Celery(
    'askmemind',
    broker=settings.resolved_celery_broker_url,
    backend=settings.resolved_celery_result_backend,
    include=['app.tasks.document_processing', 'app.tasks.password_reset', 'app.tasks.demo_cleanup'],
)

celery_app.conf.update(
    beat_schedule={"demo-expiration": {"task": "demo.cleanup", "schedule": 300.0}},
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,
)
