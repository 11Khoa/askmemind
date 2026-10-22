"""Track document processing attempts and complete chunk checkpoints.

Revision ID: c6f13b92a801
Revises: 8a7d32e901bc
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "c6f13b92a801"
down_revision = "8a7d32e901bc"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "documents", sa.Column("processing_attempt_id", postgresql.UUID(as_uuid=True))
    )
    op.add_column("documents", sa.Column("chunk_count", sa.Integer()))


def downgrade():
    op.drop_column("documents", "chunk_count")
    op.drop_column("documents", "processing_attempt_id")
