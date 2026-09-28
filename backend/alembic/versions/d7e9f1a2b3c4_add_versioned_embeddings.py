"""add versioned 2048-dimensional embeddings

Revision ID: d7e9f1a2b3c4
Revises: a81bba43dad0
Create Date: 2026-09-28 15:10:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector


revision: str = "d7e9f1a2b3c4"
down_revision: Union[str, Sequence[str], None] = "a81bba43dad0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add v2 storage without modifying legacy embeddings."""
    op.add_column(
        "chunks",
        sa.Column("embedding_v2", Vector(2048), nullable=True),
    )
    op.add_column(
        "chunks",
        sa.Column("embedding_v2_provider", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "chunks",
        sa.Column("embedding_v2_model", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "chunks",
        sa.Column("embedding_v2_dimensions", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    """Remove v2 storage while preserving legacy embeddings."""
    op.drop_column("chunks", "embedding_v2_dimensions")
    op.drop_column("chunks", "embedding_v2_model")
    op.drop_column("chunks", "embedding_v2_provider")
    op.drop_column("chunks", "embedding_v2")
