"""One immutable access scope, injected into all HTTP data repositories."""
import uuid
from dataclasses import dataclass
from sqlalchemy import select, func
from fastapi import HTTPException
from app.models.demo_session import DemoSession


@dataclass(frozen=True)
class DataScope:
    user_id: uuid.UUID
    demo_session_id: uuid.UUID | None = None
    admin: bool = False

    def conditions(self, model):
        if self.admin:
            return ()
        if self.demo_session_id is None:
            # Existing services enforce normal-user ownership, preserving their
            # established 403 semantics; never expose retained demo aggregates.
            return (model.demo_session_id.is_(None),)
        return (model.user_id == self.user_id, model.demo_session_id == self.demo_session_id)

    def check_active(self, db, *, lock=False):
        if self.demo_session_id is None:
            return
        statement = select(DemoSession.id).where(
            DemoSession.id == self.demo_session_id, DemoSession.user_id == self.user_id,
            DemoSession.expires_at > func.clock_timestamp(),
        )
        if lock:
            statement = statement.with_for_update()
        if db.scalar(statement) is None:
            raise HTTPException(status_code=410, detail="Demo session expired. Start a new demo session.")
