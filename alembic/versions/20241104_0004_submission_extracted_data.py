"""submission extracted_data fields

Revision ID: 0004
Revises: 0003
Create Date: 2024-11-04
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("submissions", sa.Column("extracted_data", JSONB, nullable=True))
    op.add_column("submissions", sa.Column("ingestion_confidence", sa.String(16), nullable=True))
    op.add_column("submissions", sa.Column("ingestion_anomalies", JSONB, nullable=True))
    op.add_column("submissions", sa.Column("missing_fields", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("submissions", "missing_fields")
    op.drop_column("submissions", "ingestion_anomalies")
    op.drop_column("submissions", "ingestion_confidence")
    op.drop_column("submissions", "extracted_data")
