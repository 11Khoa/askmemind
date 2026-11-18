from app.core.celery_app import celery_app
from app.core.config import settings
from app.database import SessionLocal
from app.services.orphan_file_cleanup import cleanup_orphan_uploads


@celery_app.task(name='storage.cleanup', ignore_result=True)
def cleanup_abandoned_uploads():
    with SessionLocal() as db:
        return cleanup_orphan_uploads(db, str(settings.resolved_upload_dir))
