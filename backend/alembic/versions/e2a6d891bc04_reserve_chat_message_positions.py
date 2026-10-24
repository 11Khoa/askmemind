"""Reserve chat message positions atomically, including pending answers.

Revision ID: e2a6d891bc04
Revises: c6f13b92a801
"""

from alembic import op
import sqlalchemy as sa

revision = "e2a6d891bc04"
down_revision = "c6f13b92a801"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("chats", sa.Column("next_message_index", sa.Integer(), nullable=False, server_default="0"))
    op.execute("""
        UPDATE chats SET next_message_index = COALESCE(
            (SELECT MAX(message_index) + 1 FROM chat_messages WHERE chat_id = chats.id), 0
        )
    """)


def downgrade():
    op.drop_column("chats", "next_message_index")
