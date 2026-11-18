from celery import Celery

from app.core.config import settings

celery_app = Celery(
    'askmemind',
    broker=settings.resolved_celery_broker_url,
    backend=settings.resolved_celery_result_backend,
    include=['app.tasks.document_processing', 'app.tasks.password_reset', 'app.tasks.demo_cleanup', 'app.tasks.document_dispatch', 'app.tasks.file_cleanup'],
)

celery_app.conf.update(
    beat_schedule={"demo-expiration": {"task": "demo.cleanup", "schedule": 300.0},
                   "document-outbox": {"task": "documents.dispatch", "schedule": 30.0},
                   "abandoned-uploads": {"task": "storage.cleanup", "schedule": 3600.0}},
    task_routes={
        "documents.process": {"queue": "documents"},
        "documents.dispatch": {"queue": "maintenance"},
        "demo.cleanup": {"queue": "maintenance"},
        "storage.cleanup": {"queue": "maintenance"},
        "auth.send_password_reset": {"queue": "maintenance"},
    },
    task_annotations={"documents.process": {
        "time_limit": settings.document_task_time_limit_seconds,
        "soft_time_limit": settings.document_task_time_limit_seconds - 30,
    }},
    task_publish_retry=False,
    broker_connection_timeout=3,
    broker_transport_options={"socket_connect_timeout": 3, "socket_timeout": 5,
                              "visibility_timeout": settings.document_task_time_limit_seconds + 600},
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,
)
