from app.core.celery_app import celery_app
from app.database import SessionLocal
from app.services.document_jobs import dispatch_pending


@celery_app.task(name="documents.dispatch", ignore_result=True)
def dispatch_document_jobs():
    with SessionLocal() as db:
        return dispatch_pending(db)
