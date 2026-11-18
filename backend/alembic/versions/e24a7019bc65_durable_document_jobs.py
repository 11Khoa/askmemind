"""Persist document dispatch intents and seed recoverable processing attempts."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
revision = "e24a7019bc65"
down_revision = "c91d2a304ef6"
branch_labels = depends_on = None


def upgrade():
    op.create_table("document_jobs",
        sa.Column("document_id", UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("attempt_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("next_dispatch_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("dispatch_count", sa.Integer(), server_default="0", nullable=False))
    op.create_index("ix_document_jobs_next_dispatch_at", "document_jobs", ["next_dispatch_at"])
    op.execute("""INSERT INTO document_jobs (document_id, attempt_id)
        SELECT id, processing_attempt_id FROM documents
        WHERE status = 'processing' AND processing_attempt_id IS NOT NULL""")


def downgrade():
    op.drop_table("document_jobs")
