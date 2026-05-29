"""widen prompt_version from VARCHAR(16) to VARCHAR(64)

Revision ID: 0006
Revises: 0005
Create Date: 2024-11-06
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("audit_trail", "prompt_version",
                    existing_type=sa.String(16), type_=sa.String(64))
    op.alter_column("cost_ledger", "prompt_version",
                    existing_type=sa.String(16), type_=sa.String(64))


def downgrade() -> None:
    op.alter_column("audit_trail", "prompt_version",
                    existing_type=sa.String(64), type_=sa.String(16))
    op.alter_column("cost_ledger", "prompt_version",
                    existing_type=sa.String(64), type_=sa.String(16))
