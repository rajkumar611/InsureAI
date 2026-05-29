"""drop audit_trail table

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-30

Audit trail is now provided by LangGraph's built-in checkpointer (state_history).
Remove the custom audit_trail table and related indexes.
"""
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_audit_trail_timestamp", table_name="audit_trail")
    op.drop_index("ix_audit_trail_policy_id", table_name="audit_trail")
    op.drop_index("ix_audit_trail_submission_id", table_name="audit_trail")
    op.drop_table("audit_trail")


def downgrade() -> None:
    pass
