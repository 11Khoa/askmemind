"""normalize user email case

Revision ID: f4b2c9d8e1a0
Revises: d7e9f1a2b3c4
Create Date: 2026-09-29 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f4b2c9d8e1a0"
down_revision: Union[str, Sequence[str], None] = "d7e9f1a2b3c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_INDEX_NAME = "ix_users_email_lower_unique"


def upgrade() -> None:
    """Normalize existing emails and enforce case-insensitive uniqueness."""
    bind = op.get_bind()
    collisions = bind.execute(
        sa.text(
            """
            SELECT lower(trim(email)) AS normalized_email,
                   array_agg(email ORDER BY email) AS emails
            FROM users
            GROUP BY lower(trim(email))
            HAVING count(*) > 1
            """
        )
    ).mappings().all()

    if collisions:
        details = "; ".join(
            f"{row['normalized_email']}: {', '.join(row['emails'])}"
            for row in collisions
        )
        raise RuntimeError(
            "Cannot normalize user emails because case-insensitive "
            f"collisions exist: {details}"
        )

    op.execute("UPDATE users SET email = lower(trim(email))")
    op.create_index(
        _INDEX_NAME,
        "users",
        [sa.text("lower(email)")],
        unique=True,
    )


def downgrade() -> None:
    """Remove the case-insensitive email uniqueness guarantee."""
    op.drop_index(_INDEX_NAME, table_name="users")
