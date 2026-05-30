"""SQLAlchemy ORM models for database tables."""
from datetime import datetime
from uuid import UUID
from sqlalchemy import Column, String, Integer, Float, DateTime, Boolean, ForeignKey, JSON, Index, Numeric, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class Submission(Base):
    """Insurance submission record."""
    __tablename__ = "submissions"
    id = Column(PGUUID(as_uuid=True), primary_key=True)
    submission_ref = Column(String(64), unique=True, nullable=False)
    broker_id = Column(String(64))
    customer_id = Column(PGUUID(as_uuid=True))
    class_of_business = Column(String(32))
    jurisdiction = Column(String(8))
    status = Column(String(32), default="RECEIVED")
    received_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    extracted_data = Column(JSONB)
    ingestion_confidence = Column(String(16))
    ingestion_anomalies = Column(JSONB)
    missing_fields = Column(JSONB)

class Broker(Base):
    """Broker/partner account."""
    __tablename__ = "brokers"
    id = Column(PGUUID(as_uuid=True), primary_key=True)
    name = Column(String(128), unique=True, nullable=False)
    email = Column(String(128), unique=True, nullable=False)
    organization = Column(String(128))
    status = Column(String(16), default="ACTIVE")
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow)

class ApiKey(Base):
    """API keys for broker authentication."""
    __tablename__ = "api_keys"
    id = Column(PGUUID(as_uuid=True), primary_key=True)
    broker_id = Column(PGUUID(as_uuid=True), ForeignKey("brokers.id", ondelete="CASCADE"), nullable=False)
    api_key_hash = Column(String(255), unique=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    last_used_at = Column(DateTime(timezone=True))

class CostEntry(Base):
    """LLM API cost tracking."""
    __tablename__ = "cost_ledger"
    id = Column(Integer, primary_key=True, autoincrement=True)
    submission_id = Column(PGUUID(as_uuid=True), ForeignKey("submissions.id"))
    policy_id = Column(String(64))
    workflow_id = Column(PGUUID(as_uuid=True))
    agent_name = Column(String(64), nullable=False)
    prompt_version = Column(String(64))
    model_id = Column(String(64), nullable=False)
    input_tokens = Column(Integer, nullable=False)
    output_tokens = Column(Integer, nullable=False)
    cost_usd = Column(Numeric(10, 6), nullable=False)
    latency_ms = Column(Integer)
    feature_tag = Column(String(64))
    class_of_business = Column(String(32))
    jurisdiction = Column(String(8))
    timestamp = Column(DateTime(timezone=True), default=datetime.utcnow)

class UnderwriterQueueItem(Base):
    """Human underwriter queue for escalated cases."""
    __tablename__ = "underwriter_queue"
    id = Column(PGUUID(as_uuid=True), primary_key=True)
    workflow_id = Column(PGUUID(as_uuid=True), unique=True, nullable=False)
    submission_id = Column(PGUUID(as_uuid=True), ForeignKey("submissions.id"), nullable=False)
    policy_id = Column(String(64))
    priority = Column(String(16), default="STANDARD")
    sla_deadline = Column(DateTime(timezone=True), nullable=False)
    assigned_underwriter_id = Column(String(64))
    locked_at = Column(DateTime(timezone=True))
    status = Column(String(32), default="PENDING")
    risk_assessment_snapshot = Column(JSONB)
    decision = Column(JSONB)
    pipeline_state_snapshot = Column(JSONB)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    completed_at = Column(DateTime(timezone=True))

class Regulation(Base):
    """Compliance regulations by jurisdiction."""
    __tablename__ = "regulations"
    id = Column(Integer, primary_key=True, autoincrement=True)
    regulator = Column(String(16), nullable=False)
    jurisdiction = Column(String(8), nullable=False)
    class_of_business = Column(String(32), nullable=False)
    rule_code = Column(String(64), nullable=False)
    rule_description = Column(String, nullable=False)
    rule_data = Column(JSONB, nullable=False)
    effective_date = Column(DateTime(timezone=True), nullable=False)
    expiry_date = Column(DateTime(timezone=True))
    version = Column(String(16), nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

class Customer(Base):
    """Customer/policyholder entity."""
    __tablename__ = "customers"
    id = Column(PGUUID(as_uuid=True), primary_key=True)
    customer_ref = Column(String(64), unique=True, nullable=False)
    entity_type = Column(String(16), nullable=False)
    full_name = Column(String(128), nullable=False)
    trading_name = Column(String(128))
    abn_nzbn = Column(String(32))
    email = Column(String(128))
    phone = Column(String(32))
    address_line1 = Column(String(128))
    city = Column(String(64))
    region = Column(String(64))
    jurisdiction = Column(String(8), nullable=False)
    kyc_status = Column(String(16), default="PENDING")
    kyc_verified_at = Column(DateTime(timezone=True))
    is_blacklisted = Column(Boolean, default=False)
    blacklist_reason = Column(String)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow)

class Policy(Base):
    """Insurance policy."""
    __tablename__ = "policies"
    id = Column(PGUUID(as_uuid=True), primary_key=True)
    policy_number = Column(String(64), unique=True, nullable=False)
    customer_id = Column(PGUUID(as_uuid=True), ForeignKey("customers.id"), nullable=False)
    submission_id = Column(PGUUID(as_uuid=True), ForeignKey("submissions.id"))
    workflow_id = Column(PGUUID(as_uuid=True))
    class_of_business = Column(String(32), nullable=False)
    jurisdiction = Column(String(8), nullable=False)
    status = Column(String(16), default="ACTIVE")
    sum_insured = Column(Numeric(18, 2), nullable=False)
    currency = Column(String(8), nullable=False)
    annual_premium = Column(Numeric(12, 2), nullable=False)
    inception_date = Column(DateTime(timezone=True), nullable=False)
    expiry_date = Column(DateTime(timezone=True), nullable=False)
    policy_conditions = Column(JSONB)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow)

class Claim(Base):
    """Historical insurance claim."""
    __tablename__ = "claims"
    id = Column(PGUUID(as_uuid=True), primary_key=True)
    claim_number = Column(String(64), unique=True, nullable=False)
    customer_id = Column(PGUUID(as_uuid=True), ForeignKey("customers.id"), nullable=False)
    policy_id = Column(PGUUID(as_uuid=True), ForeignKey("policies.id"))
    class_of_business = Column(String(32), nullable=False)
    jurisdiction = Column(String(8), nullable=False)
    risk_address_region = Column(String(128))
    claim_date = Column(DateTime(timezone=True), nullable=False)
    date_reported = Column(DateTime(timezone=True), nullable=False)
    cause_of_loss = Column(String(128), nullable=False)
    incurred_amount = Column(Numeric(18, 2))
    reserved_amount = Column(Numeric(18, 2))
    currency = Column(String(8), nullable=False)
    status = Column(String(16), default="SETTLED")
    is_large_loss = Column(Boolean, default=False)
    fraud_flag = Column(Boolean, default=False)
    fraud_investigation_status = Column(String(32))
    claim_summary = Column(String)
    settled_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow)

class ClaimsEmbedding(Base):
    """Vector embeddings for historical claims (RAG)."""
    __tablename__ = "claims_embeddings"
    id = Column(Integer, primary_key=True, autoincrement=True)
    claim_id = Column(PGUUID(as_uuid=True), ForeignKey("claims.id"), nullable=False)
    claim_summary_chunk = Column(String, nullable=False)
    embedding = Column(JSONB, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
