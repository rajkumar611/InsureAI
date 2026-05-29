"""add pipeline_state_snapshot to underwriter_queue

Revision ID: 0005
Revises: 0004
Create Date: 2024-11-05
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "underwriter_queue",
        sa.Column("pipeline_state_snapshot", JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("underwriter_queue", "pipeline_state_snapshot")
