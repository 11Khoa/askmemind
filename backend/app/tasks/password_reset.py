import logging

from app.core.celery_app import celery_app
from app.core.config import settings
from app.core.logging import log_event
from app.database import SessionLocal
from app.repositories.password_reset_repository import PasswordResetRepository
from app.repositories.user_repository import UserRepository
from app.services.password_reset_service import PasswordResetService
from app.services.reset_email_service import ResetEmailService

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True, name="auth.send_password_reset", ignore_result=True, max_retries=3
)
def send_password_reset(self, email: str, request_id: str | None = None) -> None:
    db = SessionLocal()
    try:
        service = PasswordResetService(
            UserRepository(db),
            PasswordResetRepository(db),
            ResetEmailService(settings),
        )
        service.send_reset(email)
    except Exception as error:
        db.rollback()
        log_event(
            logger,
            logging.ERROR,
            "auth.password_reset.email_failed",
            request_id=request_id,
            error_type=type(error).__name__,
        )
        # Do not let SMTP exception text or token values reach Celery logs/results.
        raise self.retry(
            exc=RuntimeError("Reset email delivery failed"), countdown=30
        ) from None
    finally:
        db.close()
