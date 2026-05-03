"""add customers, policies, claims tables; link submissions and claims_embeddings

Revision ID: 0003
Revises: 0002
Create Date: 2024-11-03
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── customers ────────────────────────────────────────────────────────────
    op.create_table(
        "customers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("customer_ref", sa.String(64), nullable=False, unique=True),
        sa.Column("entity_type", sa.String(16), nullable=False),
        sa.Column("full_name", sa.String(128), nullable=False),
        sa.Column("trading_name", sa.String(128)),
        sa.Column("abn_nzbn", sa.String(32)),
        sa.Column("email", sa.String(128)),
        sa.Column("phone", sa.String(32)),
        sa.Column("address_line1", sa.String(128)),
        sa.Column("city", sa.String(64)),
        sa.Column("region", sa.String(64)),
        sa.Column("jurisdiction", sa.String(8), nullable=False),
        sa.Column("kyc_status", sa.String(16), nullable=False, server_default="PENDING"),
        sa.Column("kyc_verified_at", sa.DateTime(timezone=True)),
        sa.Column("is_blacklisted", sa.Boolean, server_default="false"),
        sa.Column("blacklist_reason", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_customers_jurisdiction", "customers", ["jurisdiction"])
    op.create_index("ix_customers_kyc_status", "customers", ["kyc_status"])

    # ── policies ─────────────────────────────────────────────────────────────
    op.create_table(
        "policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("policy_number", sa.String(64), nullable=False, unique=True),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("submission_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("submissions.id")),
        sa.Column("workflow_id", postgresql.UUID(as_uuid=True)),
        sa.Column("class_of_business", sa.String(32), nullable=False),
        sa.Column("jurisdiction", sa.String(8), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
        sa.Column("sum_insured", sa.Numeric(18, 2), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("annual_premium", sa.Numeric(12, 2), nullable=False),
        sa.Column("inception_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expiry_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("policy_conditions", postgresql.JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_policies_customer_id", "policies", ["customer_id"])
    op.create_index("ix_policies_status", "policies", ["status"])
    op.create_index("ix_policies_expiry_date", "policies", ["expiry_date"])

    # ── claims ───────────────────────────────────────────────────────────────
    op.create_table(
        "claims",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("claim_number", sa.String(64), nullable=False, unique=True),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("policy_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("policies.id")),
        sa.Column("class_of_business", sa.String(32), nullable=False),
        sa.Column("jurisdiction", sa.String(8), nullable=False),
        sa.Column("risk_address_region", sa.String(128)),
        sa.Column("claim_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("date_reported", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cause_of_loss", sa.String(128), nullable=False),
        sa.Column("incurred_amount", sa.Numeric(18, 2)),
        sa.Column("reserved_amount", sa.Numeric(18, 2)),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="SETTLED"),
        sa.Column("is_large_loss", sa.Boolean, server_default="false"),
        sa.Column("fraud_flag", sa.Boolean, server_default="false"),
        sa.Column("fraud_investigation_status", sa.String(32)),
        sa.Column("claim_summary", sa.Text),
        sa.Column("settled_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_claims_customer_id", "claims", ["customer_id"])
    op.create_index("ix_claims_policy_id", "claims", ["policy_id"])
    op.create_index("ix_claims_claim_date", "claims", ["claim_date"])
    op.create_index("ix_claims_jurisdiction", "claims", ["jurisdiction"])
    op.create_index("ix_claims_fraud_flag", "claims", ["fraud_flag"])

    # ── link submissions → customers ─────────────────────────────────────────
    op.add_column("submissions",
        sa.Column("customer_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("customers.id"))
    )

    # ── link claims_embeddings → claims + customers ──────────────────────────
    op.add_column("claims_embeddings",
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("claims.id"))
    )
    op.add_column("claims_embeddings",
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("customers.id"))
    )
    op.create_index("ix_claims_emb_customer_id", "claims_embeddings", ["customer_id"])
    op.create_index("ix_claims_emb_claim_id", "claims_embeddings", ["claim_id"])


def downgrade() -> None:
    op.drop_index("ix_claims_emb_claim_id", "claims_embeddings")
    op.drop_index("ix_claims_emb_customer_id", "claims_embeddings")
    op.drop_column("claims_embeddings", "customer_id")
    op.drop_column("claims_embeddings", "claim_id")
    op.drop_column("submissions", "customer_id")
    op.drop_table("claims")
    op.drop_table("policies")
    op.drop_table("customers")
