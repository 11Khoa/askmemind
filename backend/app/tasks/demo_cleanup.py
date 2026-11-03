import logging
from sqlalchemy import select, func
from app.core.celery_app import celery_app
from app.database import SessionLocal
from app.models.demo_session import DemoSession
from app.services.demo_service import cleanup_session

logger = logging.getLogger(__name__)


@celery_app.task(name="demo.cleanup", ignore_result=True)
def cleanup_expired_demo_sessions():
    with SessionLocal() as db:
        # Bound each run; repeated runs drain backlog without an unbounded query.
        identifiers = db.scalars(select(DemoSession.id).where(
            DemoSession.expires_at <= func.clock_timestamp()).order_by(DemoSession.expires_at).limit(100)).all()
        for identifier in identifiers:
            try:
                cleanup_session(db, identifier)
            except Exception:
                db.rollback()
                logger.error("demo.cleanup.retry_next_sweep")
