"""initial schema

Revision ID: 0001
Revises:
Create Date: 2024-11-01
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ── submissions ──────────────────────────────────────────────────────────
    op.create_table(
        "submissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("submission_ref", sa.String(64), nullable=False, unique=True),
        sa.Column("broker_id", sa.String(64)),
        sa.Column("class_of_business", sa.String(32)),
        sa.Column("jurisdiction", sa.String(8)),
        sa.Column("status", sa.String(32), nullable=False, server_default="RECEIVED"),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("raw_document_paths", postgresql.JSONB),
    )

    # ── workflows ────────────────────────────────────────────────────────────
    op.create_table(
        "workflows",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("submission_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("policy_id", sa.String(64), unique=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="STARTED"),
        sa.Column("current_node", sa.String(64)),
        sa.Column("state_snapshot", postgresql.JSONB),
        sa.Column("error_log", postgresql.JSONB),
        sa.Column("loopback_counts", postgresql.JSONB),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── audit_trail ──────────────────────────────────────────────────────────
    op.create_table(
        "audit_trail",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("submission_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("submissions.id"), nullable=False),
        sa.Column("policy_id", sa.String(64)),
        sa.Column("workflow_id", postgresql.UUID(as_uuid=True)),
        sa.Column("agent_name", sa.String(64), nullable=False),
        sa.Column("prompt_version", sa.String(16)),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("input_payload", postgresql.JSONB),
        sa.Column("raw_llm_response", sa.Text),
        sa.Column("parsed_output", postgresql.JSONB),
        sa.Column("decision_value", sa.String(32)),
        sa.Column("decision_rationale", sa.Text),
        sa.Column("confidence_score", sa.Numeric(4, 3)),
        sa.Column("underwriter_id", sa.String(64)),
        sa.Column("override_reason", sa.Text),
        sa.Column("processing_time_ms", sa.Integer),
        sa.Column("entry_hash", sa.String(64)),
        sa.Column("previous_hash", sa.String(64)),
        sa.Column("timestamp", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_audit_trail_submission_id", "audit_trail", ["submission_id"])
    op.create_index("ix_audit_trail_policy_id", "audit_trail", ["policy_id"])
    op.create_index("ix_audit_trail_timestamp", "audit_trail", ["timestamp"])

    # ── cost_ledger ──────────────────────────────────────────────────────────
    op.create_table(
        "cost_ledger",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("submission_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("submissions.id")),
        sa.Column("policy_id", sa.String(64)),
        sa.Column("workflow_id", postgresql.UUID(as_uuid=True)),
        sa.Column("agent_name", sa.String(64), nullable=False),
        sa.Column("prompt_version", sa.String(16)),
        sa.Column("model_id", sa.String(64), nullable=False),
        sa.Column("input_tokens", sa.Integer, nullable=False),
        sa.Column("output_tokens", sa.Integer, nullable=False),
        sa.Column("cost_usd", sa.Numeric(10, 6), nullable=False),
        sa.Column("latency_ms", sa.Integer),
        sa.Column("feature_tag", sa.String(64)),
        sa.Column("class_of_business", sa.String(32)),
        sa.Column("jurisdiction", sa.String(8)),
        sa.Column("timestamp", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_cost_ledger_policy_id", "cost_ledger", ["policy_id"])
    op.create_index("ix_cost_ledger_agent_name", "cost_ledger", ["agent_name"])
    op.create_index("ix_cost_ledger_timestamp", "cost_ledger", ["timestamp"])

    # ── regulations ──────────────────────────────────────────────────────────
    op.create_table(
        "regulations",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("regulator", sa.String(16), nullable=False),
        sa.Column("jurisdiction", sa.String(8), nullable=False),
        sa.Column("class_of_business", sa.String(32), nullable=False),
        sa.Column("rule_code", sa.String(64), nullable=False),
        sa.Column("rule_description", sa.Text, nullable=False),
        sa.Column("rule_data", postgresql.JSONB, nullable=False),
        sa.Column("effective_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expiry_date", sa.DateTime(timezone=True)),
        sa.Column("version", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("rule_code", "version", name="uq_regulation_rule_version"),
    )
    op.create_index(
        "ix_regulations_active", "regulations",
        ["jurisdiction", "class_of_business", "expiry_date"]
    )

    # ── claims_embeddings ────────────────────────────────────────────────────
    op.create_table(
        "claims_embeddings",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("customer_ref", sa.String(64)),
        sa.Column("risk_address_region", sa.String(128)),
        sa.Column("class_of_business", sa.String(32), nullable=False),
        sa.Column("jurisdiction", sa.String(8), nullable=False),
        sa.Column("claim_date", sa.DateTime(timezone=True)),
        sa.Column("cause_of_loss", sa.String(128)),
        sa.Column("incurred_amount", sa.Numeric(18, 2)),
        sa.Column("currency", sa.String(8)),
        sa.Column("is_large_loss", sa.Boolean, server_default="false"),
        sa.Column("fraud_flag", sa.Boolean, server_default="false"),
        sa.Column("claim_summary", sa.Text),
        sa.Column("embedding", postgresql.ARRAY(sa.Float)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.execute("""
        ALTER TABLE claims_embeddings
        ALTER COLUMN embedding TYPE vector(1536)
        USING embedding::vector(1536)
    """)
    op.execute("""
        CREATE INDEX ix_claims_embedding_vector
        ON claims_embeddings
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
    """)
    op.create_index("ix_claims_customer_ref", "claims_embeddings", ["customer_ref"])
    op.create_index(
        "ix_claims_class_jurisdiction", "claims_embeddings",
        ["class_of_business", "jurisdiction"]
    )

    # ── underwriter_queue ────────────────────────────────────────────────────
    op.create_table(
        "underwriter_queue",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workflow_id", postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("submission_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("submissions.id"), nullable=False),
        sa.Column("policy_id", sa.String(64)),
        sa.Column("priority", sa.String(16), nullable=False, server_default="STANDARD"),
        sa.Column("sla_deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("assigned_underwriter_id", sa.String(64)),
        sa.Column("locked_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(32), nullable=False, server_default="PENDING"),
        sa.Column("risk_assessment_snapshot", postgresql.JSONB),
        sa.Column("decision", postgresql.JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_queue_status_priority", "underwriter_queue", ["status", "priority"])
    op.create_index("ix_queue_sla_deadline", "underwriter_queue", ["sla_deadline"])


def downgrade() -> None:
    op.drop_table("underwriter_queue")
    op.drop_table("claims_embeddings")
    op.drop_table("regulations")
    op.drop_table("cost_ledger")
    op.drop_table("audit_trail")
    op.drop_table("workflows")
    op.drop_table("submissions")
    op.execute("DROP EXTENSION IF EXISTS vector")
