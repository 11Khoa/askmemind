from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import delete, select, func
from sqlalchemy.orm import Session

from app.database import engine
from app.models.user import User
from app.models.audit_event import AuditEvent
from app.schemas.admin import AdminUserUpdate
from app.services.admin_service import update_user


def test_two_admins_cannot_concurrently_remove_the_last_administrator():
    ids = [uuid4(), uuid4()]
    with Session(engine) as db:
        db.add_all([User(id=id, email=f"{id}@example.com", hashed_password="hashed", role="admin") for id in ids])
        db.commit()
    barrier = Barrier(2)
    def demote(id):
        with Session(engine) as db:
            barrier.wait(timeout=10)
            try:
                update_user(db, id, id, AdminUserUpdate(role="user"))
                return 200
            except HTTPException as error:
                return error.status_code
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sorted(pool.map(demote, ids)) == [200, 409]
        with Session(engine) as db:
            assert db.scalar(select(func.count()).select_from(User).where(User.id.in_(ids), User.role == "admin")) == 1
    finally:
        with Session(engine) as db:
            db.execute(delete(AuditEvent).where(AuditEvent.actor_id.in_(ids)))
            db.execute(delete(User).where(User.id.in_(ids)))
            db.commit()
