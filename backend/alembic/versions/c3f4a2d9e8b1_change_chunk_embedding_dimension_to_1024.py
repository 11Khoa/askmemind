"""change chunk embedding dimension to 1024

Revision ID: c3f4a2d9e8b1
Revises: b1c0356b1fa1
Create Date: 2026-07-07 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "c3f4a2d9e8b1"
down_revision: Union[str, Sequence[str], None] = "b1c0356b1fa1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        "ALTER TABLE chunks "
        "ALTER COLUMN embedding TYPE vector(1024) "
        "USING embedding::vector(1024)"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        "ALTER TABLE chunks "
        "ALTER COLUMN embedding TYPE vector(1536) "
        "USING embedding::vector(1536)"
    )
