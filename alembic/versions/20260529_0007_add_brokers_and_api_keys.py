"""add brokers and api_keys tables for external API authentication

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-29
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create brokers table
    op.create_table(
        "brokers",
        sa.Column("id", UUID(as_uuid=True), nullable=False, primary_key=True),
        sa.Column("name", sa.String(128), nullable=False, unique=True),
        sa.Column("email", sa.String(128), nullable=False, unique=True),
        sa.Column("organization", sa.String(128), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index("ix_brokers_status", "brokers", ["status"])
    op.create_index("ix_brokers_email", "brokers", ["email"])

    # Create api_keys table
    op.create_table(
        "api_keys",
        sa.Column("id", UUID(as_uuid=True), nullable=False, primary_key=True),
        sa.Column("broker_id", UUID(as_uuid=True), nullable=False),
        sa.Column("api_key_hash", sa.String(255), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["broker_id"], ["brokers.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_api_keys_broker_id", "api_keys", ["broker_id"])
    op.create_index("ix_api_keys_api_key_hash", "api_keys", ["api_key_hash"])


def downgrade() -> None:
    op.drop_index("ix_api_keys_api_key_hash", table_name="api_keys")
    op.drop_index("ix_api_keys_broker_id", table_name="api_keys")
    op.drop_table("api_keys")

    op.drop_index("ix_brokers_email", table_name="brokers")
    op.drop_index("ix_brokers_status", table_name="brokers")
    op.drop_table("brokers")
