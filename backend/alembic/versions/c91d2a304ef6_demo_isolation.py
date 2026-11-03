"""Isolate shared demo accounts by browser session."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
revision = "c91d2a304ef6"
down_revision = "b84e1c720ad3"
branch_labels = depends_on = None


def upgrade():
    op.add_column("users", sa.Column("is_demo", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("users", sa.Column("demo_retention_minutes", sa.Integer(), server_default="60", nullable=False))
    op.add_column("users", sa.Column("demo_upload_enabled", sa.Boolean(), server_default=sa.true(), nullable=False))
    op.create_check_constraint("ck_users_demo_retention", "users", "demo_retention_minutes BETWEEN 15 AND 1440")
    op.create_check_constraint("ck_users_demo_role", "users", "NOT is_demo OR role = 'user'")
    op.create_table("demo_sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("notice_version", sa.String(64), server_default="", nullable=False),
        sa.Column("notice_accepted_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False))
    for field in ("user_id", "expires_at"):
        op.create_index(f"ix_demo_sessions_{field}", "demo_sessions", [field])
    for table in ("documents", "chats"):
        op.add_column(table, sa.Column("demo_session_id", UUID(as_uuid=True), nullable=True))
        op.create_foreign_key(f"fk_{table}_demo_session", table, "demo_sessions", ["demo_session_id"], ["id"], ondelete="CASCADE")
        op.create_index(f"ix_{table}_demo_session_id", table, ["demo_session_id"])


def downgrade():
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM demo_sessions) THEN
        RAISE EXCEPTION 'Clean all demo sessions using the cleanup service before downgrading';
      END IF;
    END $$;""")
    for table in ("chats", "documents"):
        op.drop_index(f"ix_{table}_demo_session_id", table)
        op.drop_constraint(f"fk_{table}_demo_session", table, type_="foreignkey")
        op.drop_column(table, "demo_session_id")
    op.drop_table("demo_sessions")
    op.drop_constraint("ck_users_demo_role", "users")
    op.drop_constraint("ck_users_demo_retention", "users")
    for field in ("demo_upload_enabled", "demo_retention_minutes", "is_demo"):
        op.drop_column("users", field)
