"""Retain security and activity events independently of deleted resources."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "a71c8d5e290f"
down_revision = "f61d09ea274b"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("audit_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True)),
        sa.Column("target_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True)),
        sa.Column("outcome", sa.String(20), nullable=False),
        sa.Column("request_id", sa.String(128)),
        sa.Column("details", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    for column in ("actor_id", "target_user_id", "action", "created_at"):
        op.create_index(f"ix_audit_events_{column}", "audit_events", [column])


def downgrade():
    op.drop_table("audit_events")
