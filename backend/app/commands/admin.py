"""Explicit, server-side bootstrap of the first administrator."""
import argparse

from sqlalchemy import select, text

from app.database import SessionLocal
from app.models.user import User


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["bootstrap"])
    parser.add_argument("--email", required=True)
    args = parser.parse_args()
    with SessionLocal() as db, db.begin():
        db.execute(text("SELECT pg_advisory_xact_lock(742091)"))
        if db.scalar(select(User.id).where(User.role == "admin", User.is_active.is_(True)).limit(1)):
            parser.error("An active administrator already exists; use the admin interface.")
        user = db.scalar(select(User).where(User.email == args.email.strip().lower()).with_for_update())
        if user is None or not user.is_active:
            parser.error("An active existing account is required.")
        user.role = "admin"
    print("Administrator bootstrapped. No password or session credentials were changed.")


if __name__ == "__main__":
    main()
