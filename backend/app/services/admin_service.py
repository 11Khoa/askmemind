from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException

from app.core.security import hash_password
from app.models.user import User
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.services.audit_service import record_audit


def lock_admin(db, actor_id):
    # Serialize changes to admin membership, including bootstrap, so two admins
    # cannot simultaneously remove each other and leave zero active admins.
    db.execute(text("SELECT pg_advisory_xact_lock(742091)"))
    actor = db.scalar(select(User).where(User.id == actor_id).execution_options(populate_existing=True))
    if actor is None or not actor.is_active or actor.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator permission required")
    return actor


def create_user(db, actor_id, payload):
    lock_admin(db, actor_id)
    user = User(email=payload.email, hashed_password=hash_password(payload.password), role=payload.role)
    db.add(user)
    try:
        db.flush()
        record_audit(db, actor_id, "admin.user.create", user.id, user.id, {"role": user.role})
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Email already registered") from None
    db.refresh(user)
    return user


def update_user(db, actor_id, user_id, payload):
    lock_admin(db, actor_id)
    user = db.scalar(select(User).where(User.id == user_id).with_for_update().execution_options(populate_existing=True))
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    new_role = payload.role if payload.role is not None else user.role
    new_active = payload.is_active if payload.is_active is not None else user.is_active
    if user.role == "admin" and user.is_active and (new_role != "admin" or not new_active):
        count = db.scalar(select(func.count()).select_from(User).where(User.role == "admin", User.is_active.is_(True)))
        if count <= 1:
            raise HTTPException(status_code=409, detail="Cannot remove the last active administrator")
    previous = {"role": user.role, "is_active": user.is_active}
    if new_role != user.role or new_active != user.is_active:
        user.role, user.is_active = new_role, new_active
        user.token_version += 1
        # This repository commits, so flush the audit in the same transaction.
        record_audit(db, actor_id, "admin.user.update", user.id, user.id, {
            "before": previous, "after": {"role": new_role, "is_active": new_active},
        })
        from datetime import datetime, timezone
        RefreshTokenRepository(db).revoke_all_for_user(user.id, datetime.now(timezone.utc))
    else:
        db.commit()
    db.refresh(user)
    return user
