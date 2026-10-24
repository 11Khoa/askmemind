"""Add user/admin roles; existing accounts remain ordinary users."""
from alembic import op
import sqlalchemy as sa

revision = "f61d09ea274b"
down_revision = "e2a6d891bc04"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("role", sa.String(10), nullable=False, server_default="user"))
    op.create_check_constraint("ck_users_role", "users", "role IN ('user', 'admin')")


def downgrade():
    op.drop_constraint("ck_users_role", "users", type_="check")
    op.drop_column("users", "role")
