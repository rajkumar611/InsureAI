"""
SQLAlchemy 2.0 ORM models for AI-Underwriting-System.

Tables:
  customers          — registered customers (individuals and companies)
  submissions        — one row per broker submission
  workflows          — LangGraph workflow state per submission
  policies           — issued insurance policies
  claims             — transactional claim records per customer/policy
  audit_trail        — immutable decision log (append-only, hash-chained)
  cost_ledger        — every LLM call cost record (append-only)
  regulations        — versioned regulatory rules (compliance agent reads these)
  claims_embeddings  — vector store for claims history RAG (pgvector)
  underwriter_queue  — human review cases and their decisions
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ─── Customers ────────────────────────────────────────────────────────────────

class Customer(Base):
    """
    Registered customer — individual or company.
    Created at first contact. KYC must be VERIFIED before policy issuance.
    """

    __tablename__ = "customers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_ref: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(16), nullable=False)  # INDIVIDUAL | COMPANY
    full_name: Mapped[str] = mapped_column(String(128), nullable=False)
    trading_name: Mapped[str | None] = mapped_column(String(128))
    abn_nzbn: Mapped[str | None] = mapped_column(String(32))  # NZ Business Number or AU Business Number
    email: Mapped[str | None] = mapped_column(String(128))
    phone: Mapped[str | None] = mapped_column(String(32))
    address_line1: Mapped[str | None] = mapped_column(String(128))
    city: Mapped[str | None] = mapped_column(String(64))
    region: Mapped[str | None] = mapped_column(String(64))
    jurisdiction: Mapped[str] = mapped_column(String(8), nullable=False)  # NZ | AU
    kyc_status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING")
    kyc_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_blacklisted: Mapped[bool] = mapped_column(Boolean, default=False)
    blacklist_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    submissions: Mapped[list[Submission]] = relationship(back_populates="customer")
    policies: Mapped[list[Policy]] = relationship(back_populates="customer")
    claims: Mapped[list[Claim]] = relationship(back_populates="customer")

    __table_args__ = (
        Index("ix_customers_jurisdiction", "jurisdiction"),
        Index("ix_customers_kyc_status", "kyc_status"),
    )


# ─── Submissions ──────────────────────────────────────────────────────────────

class Submission(Base):
    """One row per broker submission received."""

    __tablename__ = "submissions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("customers.id"))
    submission_ref: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    broker_id: Mapped[str | None] = mapped_column(String(64))
    class_of_business: Mapped[str | None] = mapped_column(String(32))
    jurisdiction: Mapped[str | None] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(32), default="RECEIVED")
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    raw_document_paths: Mapped[dict | None] = mapped_column(JSONB)
    extracted_data: Mapped[dict | None] = mapped_column(JSONB)
    ingestion_confidence: Mapped[str | None] = mapped_column(String(16))
    ingestion_anomalies: Mapped[list | None] = mapped_column(JSONB)
    missing_fields: Mapped[list | None] = mapped_column(JSONB)

    customer: Mapped[Customer | None] = relationship(back_populates="submissions")
    workflow: Mapped[Workflow | None] = relationship(back_populates="submission", uselist=False)
    audit_entries: Mapped[list[AuditEntry]] = relationship(back_populates="submission")
    cost_entries: Mapped[list[CostEntry]] = relationship(back_populates="submission")
    policy: Mapped[Policy | None] = relationship(back_populates="submission", uselist=False)


# ─── Workflows ────────────────────────────────────────────────────────────────

class Workflow(Base):
    """
    LangGraph workflow state per submission.
    State is stored as JSONB — LangGraph checkpointer writes here.
    """

    __tablename__ = "workflows"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    submission_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("submissions.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    policy_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(String(32), default="STARTED")
    current_node: Mapped[str | None] = mapped_column(String(64))
    state_snapshot: Mapped[dict | None] = mapped_column(JSONB)
    error_log: Mapped[list | None] = mapped_column(JSONB)
    loopback_counts: Mapped[dict | None] = mapped_column(JSONB)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    submission: Mapped[Submission] = relationship(back_populates="workflow")


# ─── Policies ─────────────────────────────────────────────────────────────────

class Policy(Base):
    """
    Issued insurance policy.
    Created only when a workflow completes successfully and governance approves.
    """

    __tablename__ = "policies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    policy_number: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customers.id"), nullable=False)
    submission_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("submissions.id"))
    workflow_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    class_of_business: Mapped[str] = mapped_column(String(32), nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ACTIVE")
    sum_insured: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    annual_premium: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    inception_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expiry_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    policy_conditions: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    customer: Mapped[Customer] = relationship(back_populates="policies")
    submission: Mapped[Submission | None] = relationship(back_populates="policy")
    claims: Mapped[list[Claim]] = relationship(back_populates="policy")

    __table_args__ = (
        Index("ix_policies_customer_id", "customer_id"),
        Index("ix_policies_status", "status"),
        Index("ix_policies_expiry_date", "expiry_date"),
    )


# ─── Claims ───────────────────────────────────────────────────────────────────

class Claim(Base):
    """
    Transactional claim record.
    Each claim is linked to a customer and optionally a policy.
    One embedding record is generated per claim for RAG similarity search.
    """

    __tablename__ = "claims"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    claim_number: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customers.id"), nullable=False)
    policy_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("policies.id"))
    class_of_business: Mapped[str] = mapped_column(String(32), nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String(8), nullable=False)
    risk_address_region: Mapped[str | None] = mapped_column(String(128))
    claim_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    date_reported: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    cause_of_loss: Mapped[str] = mapped_column(String(128), nullable=False)
    incurred_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    reserved_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="SETTLED")
    is_large_loss: Mapped[bool] = mapped_column(Boolean, default=False)
    fraud_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    fraud_investigation_status: Mapped[str | None] = mapped_column(String(32))
    claim_summary: Mapped[str | None] = mapped_column(Text)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    customer: Mapped[Customer] = relationship(back_populates="claims")
    policy: Mapped[Policy | None] = relationship(back_populates="claims")
    embedding: Mapped[ClaimsEmbedding | None] = relationship(back_populates="claim", uselist=False)

    __table_args__ = (
        Index("ix_claims_customer_id", "customer_id"),
        Index("ix_claims_policy_id", "policy_id"),
        Index("ix_claims_claim_date", "claim_date"),
        Index("ix_claims_jurisdiction", "jurisdiction"),
        Index("ix_claims_fraud_flag", "fraud_flag"),
    )


# ─── Audit Trail ──────────────────────────────────────────────────────────────

class AuditEntry(Base):
    """
    Immutable decision log. Append-only — never updated or deleted.
    Hash-chained: each entry includes the hash of the previous entry.
    """

    __tablename__ = "audit_trail"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    submission_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("submissions.id"), nullable=False)
    policy_id: Mapped[str | None] = mapped_column(String(64))
    workflow_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    agent_name: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_version: Mapped[str | None] = mapped_column(String(16))
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    input_payload: Mapped[dict | None] = mapped_column(JSONB)
    raw_llm_response: Mapped[str | None] = mapped_column(Text)
    parsed_output: Mapped[dict | None] = mapped_column(JSONB)
    decision_value: Mapped[str | None] = mapped_column(String(32))
    decision_rationale: Mapped[str | None] = mapped_column(Text)
    confidence_score: Mapped[float | None] = mapped_column(Numeric(4, 3))
    underwriter_id: Mapped[str | None] = mapped_column(String(64))
    override_reason: Mapped[str | None] = mapped_column(Text)
    processing_time_ms: Mapped[int | None] = mapped_column(Integer)
    entry_hash: Mapped[str | None] = mapped_column(String(64))
    previous_hash: Mapped[str | None] = mapped_column(String(64))
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    submission: Mapped[Submission] = relationship(back_populates="audit_entries")

    __table_args__ = (
        Index("ix_audit_trail_submission_id", "submission_id"),
        Index("ix_audit_trail_policy_id", "policy_id"),
        Index("ix_audit_trail_timestamp", "timestamp"),
    )


# ─── Cost Ledger ──────────────────────────────────────────────────────────────

class CostEntry(Base):
    """
    Append-only LLM cost record. Every LLM call writes one row.
    Never updated. Never deleted.
    """

    __tablename__ = "cost_ledger"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    submission_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("submissions.id"))
    policy_id: Mapped[str | None] = mapped_column(String(64))
    workflow_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    agent_name: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_version: Mapped[str | None] = mapped_column(String(16))
    model_id: Mapped[str] = mapped_column(String(64), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    feature_tag: Mapped[str | None] = mapped_column(String(64))
    class_of_business: Mapped[str | None] = mapped_column(String(32))
    jurisdiction: Mapped[str | None] = mapped_column(String(8))
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    submission: Mapped[Submission | None] = relationship(back_populates="cost_entries")

    __table_args__ = (
        Index("ix_cost_ledger_policy_id", "policy_id"),
        Index("ix_cost_ledger_agent_name", "agent_name"),
        Index("ix_cost_ledger_timestamp", "timestamp"),
    )


# ─── Regulations ──────────────────────────────────────────────────────────────

class Regulation(Base):
    """
    Versioned regulatory rules. Compliance agent reads active rules at runtime.
    Rules are never deleted — expired rules get an expiry_date.
    """

    __tablename__ = "regulations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    regulator: Mapped[str] = mapped_column(String(16), nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String(8), nullable=False)
    class_of_business: Mapped[str] = mapped_column(String(32), nullable=False)
    rule_code: Mapped[str] = mapped_column(String(64), nullable=False)
    rule_description: Mapped[str] = mapped_column(Text, nullable=False)
    rule_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    effective_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expiry_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_regulations_active", "jurisdiction", "class_of_business", "expiry_date"),
        UniqueConstraint("rule_code", "version", name="uq_regulation_rule_version"),
    )


# ─── Claims Embeddings (Vector Store for RAG) ─────────────────────────────────

class ClaimsEmbedding(Base):
    """
    Vector store for claims history RAG.
    Each row is one historical claim, embedded for similarity search.
    Linked back to the source Claim and Customer for direct lookup.
    pgvector extension required.
    """

    __tablename__ = "claims_embeddings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    claim_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("claims.id"))
    customer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("customers.id"))
    customer_ref: Mapped[str | None] = mapped_column(String(64))
    risk_address_region: Mapped[str | None] = mapped_column(String(128))
    class_of_business: Mapped[str] = mapped_column(String(32), nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String(8), nullable=False)
    claim_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cause_of_loss: Mapped[str | None] = mapped_column(String(128))
    incurred_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    currency: Mapped[str | None] = mapped_column(String(8))
    is_large_loss: Mapped[bool] = mapped_column(Boolean, default=False)
    fraud_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    claim_summary: Mapped[str | None] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(384))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    claim: Mapped[Claim | None] = relationship(back_populates="embedding")

    __table_args__ = (
        Index(
            "ix_claims_embedding_vector",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("ix_claims_customer_ref", "customer_ref"),
        Index("ix_claims_class_jurisdiction", "class_of_business", "jurisdiction"),
        Index("ix_claims_emb_customer_id", "customer_id"),
        Index("ix_claims_emb_claim_id", "claim_id"),
    )


# ─── Underwriter Queue ────────────────────────────────────────────────────────

class UnderwriterQueueItem(Base):
    """
    Human-in-the-loop review queue.
    Cases waiting for or completed by underwriter review.
    """

    __tablename__ = "underwriter_queue"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, unique=True)
    submission_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("submissions.id"), nullable=False)
    policy_id: Mapped[str | None] = mapped_column(String(64))
    priority: Mapped[str] = mapped_column(String(16), default="STANDARD")
    sla_deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    assigned_underwriter_id: Mapped[str | None] = mapped_column(String(64))
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), default="PENDING")
    risk_assessment_snapshot: Mapped[dict | None] = mapped_column(JSONB)
    decision: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_queue_status_priority", "status", "priority"),
        Index("ix_queue_sla_deadline", "sla_deadline"),
    )
