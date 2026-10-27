"""Persist per-page extraction checkpoints and resumable processing progress."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "b84e1c720ad3"
down_revision = "a71c8d5e290f"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("documents", sa.Column("processing_progress", postgresql.JSONB(), nullable=True))
    op.create_table(
        "document_page_checkpoints",
        sa.Column("document_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("page_number", sa.Integer(), primary_key=True),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("extraction_metadata", postgresql.JSONB(), nullable=False),
    )


def downgrade():
    op.drop_table("document_page_checkpoints")
    op.drop_column("documents", "processing_progress")
