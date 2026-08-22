"""add chunks content fts gin index

Revision ID: a81bba43dad0
Revises: c3f4a2d9e8b1
Create Date: 2026-08-22 19:28:45.812542

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'a81bba43dad0'
down_revision: Union[str, Sequence[str], None] = 'c3f4a2d9e8b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        "CREATE INDEX ix_chunks_content_fts "
        "ON chunks "
        "USING GIN (to_tsvector('simple'::regconfig, content))"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        "DROP INDEX ix_chunks_content_fts"
    )
