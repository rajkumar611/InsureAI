-- INSUREAI Database Schema
-- Complete schema generated from all migrations
-- Run once: psql -U qbe -d aus_underwriting -f schema.sql

CREATE EXTENSION IF NOT EXISTS vector;

-- ────────────────────────────────────────────────────────────────────────────
-- CORE TABLES
-- ────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS submissions (
    id UUID PRIMARY KEY,
    submission_ref VARCHAR(64) NOT NULL UNIQUE,
    broker_id VARCHAR(64),
    customer_id UUID,
    class_of_business VARCHAR(32),
    jurisdiction VARCHAR(8),
    status VARCHAR(32) NOT NULL DEFAULT 'RECEIVED',
    received_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    raw_document_paths JSONB,
    extracted_data JSONB,
    ingestion_confidence VARCHAR(16),
    ingestion_anomalies JSONB,
    missing_fields JSONB
);

CREATE TABLE IF NOT EXISTS workflows (
    id UUID PRIMARY KEY,
    submission_id UUID NOT NULL UNIQUE,
    policy_id VARCHAR(64) UNIQUE,
    status VARCHAR(32) NOT NULL DEFAULT 'STARTED',
    current_node VARCHAR(64),
    state_snapshot JSONB,
    error_log JSONB,
    loopback_counts JSONB,
    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    FOREIGN KEY (submission_id) REFERENCES submissions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS cost_ledger (
    id BIGSERIAL PRIMARY KEY,
    submission_id UUID,
    policy_id VARCHAR(64),
    workflow_id UUID,
    agent_name VARCHAR(64) NOT NULL,
    prompt_version VARCHAR(64),
    model_id VARCHAR(64) NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    cost_usd NUMERIC(10, 6) NOT NULL,
    latency_ms INTEGER,
    feature_tag VARCHAR(64),
    class_of_business VARCHAR(32),
    jurisdiction VARCHAR(8),
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    FOREIGN KEY (submission_id) REFERENCES submissions(id)
);

CREATE TABLE IF NOT EXISTS regulations (
    id SERIAL PRIMARY KEY,
    regulator VARCHAR(16) NOT NULL,
    jurisdiction VARCHAR(8) NOT NULL,
    class_of_business VARCHAR(32) NOT NULL,
    rule_code VARCHAR(64) NOT NULL,
    rule_description TEXT NOT NULL,
    rule_data JSONB NOT NULL,
    effective_date TIMESTAMP WITH TIME ZONE NOT NULL,
    expiry_date TIMESTAMP WITH TIME ZONE,
    version VARCHAR(16) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(rule_code, version)
);

CREATE TABLE IF NOT EXISTS claims_embeddings (
    id BIGSERIAL PRIMARY KEY,
    customer_ref VARCHAR(64),
    customer_id UUID,
    claim_id UUID,
    risk_address_region VARCHAR(128),
    class_of_business VARCHAR(32) NOT NULL,
    jurisdiction VARCHAR(8) NOT NULL,
    claim_date TIMESTAMP WITH TIME ZONE,
    cause_of_loss VARCHAR(128),
    incurred_amount NUMERIC(18, 2),
    currency VARCHAR(8),
    is_large_loss BOOLEAN DEFAULT false,
    fraud_flag BOOLEAN DEFAULT false,
    claim_summary TEXT,
    embedding vector(384),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    FOREIGN KEY (customer_id) REFERENCES customers(id),
    FOREIGN KEY (claim_id) REFERENCES claims(id)
);

CREATE TABLE IF NOT EXISTS underwriter_queue (
    id UUID PRIMARY KEY,
    workflow_id UUID NOT NULL UNIQUE,
    submission_id UUID NOT NULL,
    policy_id VARCHAR(64),
    priority VARCHAR(16) NOT NULL DEFAULT 'STANDARD',
    sla_deadline TIMESTAMP WITH TIME ZONE NOT NULL,
    assigned_underwriter_id VARCHAR(64),
    locked_at TIMESTAMP WITH TIME ZONE,
    status VARCHAR(32) NOT NULL DEFAULT 'PENDING',
    risk_assessment_snapshot JSONB,
    decision JSONB,
    pipeline_state_snapshot JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    FOREIGN KEY (submission_id) REFERENCES submissions(id)
);

-- ────────────────────────────────────────────────────────────────────────────
-- CUSTOMER & POLICY TABLES
-- ────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS customers (
    id UUID PRIMARY KEY,
    customer_ref VARCHAR(64) NOT NULL UNIQUE,
    entity_type VARCHAR(16) NOT NULL,
    full_name VARCHAR(128) NOT NULL,
    trading_name VARCHAR(128),
    abn_nzbn VARCHAR(32),
    email VARCHAR(128),
    phone VARCHAR(32),
    address_line1 VARCHAR(128),
    city VARCHAR(64),
    region VARCHAR(64),
    jurisdiction VARCHAR(8) NOT NULL,
    kyc_status VARCHAR(16) NOT NULL DEFAULT 'PENDING',
    kyc_verified_at TIMESTAMP WITH TIME ZONE,
    is_blacklisted BOOLEAN DEFAULT false,
    blacklist_reason TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS policies (
    id UUID PRIMARY KEY,
    policy_number VARCHAR(64) NOT NULL UNIQUE,
    customer_id UUID NOT NULL,
    submission_id UUID,
    workflow_id UUID,
    class_of_business VARCHAR(32) NOT NULL,
    jurisdiction VARCHAR(8) NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'ACTIVE',
    sum_insured NUMERIC(18, 2) NOT NULL,
    currency VARCHAR(8) NOT NULL,
    annual_premium NUMERIC(12, 2) NOT NULL,
    inception_date TIMESTAMP WITH TIME ZONE NOT NULL,
    expiry_date TIMESTAMP WITH TIME ZONE NOT NULL,
    policy_conditions JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    FOREIGN KEY (customer_id) REFERENCES customers(id)
);

CREATE TABLE IF NOT EXISTS claims (
    id UUID PRIMARY KEY,
    claim_number VARCHAR(64) NOT NULL UNIQUE,
    customer_id UUID NOT NULL,
    policy_id UUID,
    class_of_business VARCHAR(32) NOT NULL,
    jurisdiction VARCHAR(8) NOT NULL,
    risk_address_region VARCHAR(128),
    claim_date TIMESTAMP WITH TIME ZONE NOT NULL,
    date_reported TIMESTAMP WITH TIME ZONE NOT NULL,
    cause_of_loss VARCHAR(128) NOT NULL,
    incurred_amount NUMERIC(18, 2),
    reserved_amount NUMERIC(18, 2),
    currency VARCHAR(8) NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'SETTLED',
    is_large_loss BOOLEAN DEFAULT false,
    fraud_flag BOOLEAN DEFAULT false,
    fraud_investigation_status VARCHAR(32),
    claim_summary TEXT,
    settled_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    FOREIGN KEY (customer_id) REFERENCES customers(id),
    FOREIGN KEY (policy_id) REFERENCES policies(id)
);

-- ────────────────────────────────────────────────────────────────────────────
-- BROKER & API KEY TABLES
-- ────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS brokers (
    id UUID PRIMARY KEY,
    name VARCHAR(128) NOT NULL UNIQUE,
    email VARCHAR(128) NOT NULL UNIQUE,
    organization VARCHAR(128),
    status VARCHAR(16) NOT NULL DEFAULT 'ACTIVE',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS api_keys (
    id UUID PRIMARY KEY,
    broker_id UUID NOT NULL,
    api_key_hash VARCHAR(255) NOT NULL UNIQUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    last_used_at TIMESTAMP WITH TIME ZONE,
    FOREIGN KEY (broker_id) REFERENCES brokers(id) ON DELETE CASCADE
);

-- ────────────────────────────────────────────────────────────────────────────
-- INDEXES
-- ────────────────────────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS ix_submissions_submission_ref ON submissions(submission_ref);
CREATE INDEX IF NOT EXISTS ix_submissions_customer_id ON submissions(customer_id);
CREATE INDEX IF NOT EXISTS ix_submissions_status ON submissions(status);

CREATE INDEX IF NOT EXISTS ix_workflows_submission_id ON workflows(submission_id);
CREATE INDEX IF NOT EXISTS ix_workflows_status ON workflows(status);

CREATE INDEX IF NOT EXISTS ix_cost_ledger_policy_id ON cost_ledger(policy_id);
CREATE INDEX IF NOT EXISTS ix_cost_ledger_agent_name ON cost_ledger(agent_name);
CREATE INDEX IF NOT EXISTS ix_cost_ledger_timestamp ON cost_ledger(timestamp);
CREATE INDEX IF NOT EXISTS ix_cost_ledger_submission_id ON cost_ledger(submission_id);

CREATE INDEX IF NOT EXISTS ix_regulations_active ON regulations(jurisdiction, class_of_business, expiry_date);

CREATE INDEX IF NOT EXISTS ix_claims_embeddings_customer_ref ON claims_embeddings(customer_ref);
CREATE INDEX IF NOT EXISTS ix_claims_embeddings_class_jurisdiction ON claims_embeddings(class_of_business, jurisdiction);
CREATE INDEX IF NOT EXISTS ix_claims_embeddings_customer_id ON claims_embeddings(customer_id);
CREATE INDEX IF NOT EXISTS ix_claims_embeddings_claim_id ON claims_embeddings(claim_id);
CREATE INDEX IF NOT EXISTS ix_claims_embedding_vector ON claims_embeddings USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS ix_underwriter_queue_status_priority ON underwriter_queue(status, priority);
CREATE INDEX IF NOT EXISTS ix_underwriter_queue_sla_deadline ON underwriter_queue(sla_deadline);

CREATE INDEX IF NOT EXISTS ix_customers_jurisdiction ON customers(jurisdiction);
CREATE INDEX IF NOT EXISTS ix_customers_kyc_status ON customers(kyc_status);

CREATE INDEX IF NOT EXISTS ix_policies_customer_id ON policies(customer_id);
CREATE INDEX IF NOT EXISTS ix_policies_status ON policies(status);
CREATE INDEX IF NOT EXISTS ix_policies_expiry_date ON policies(expiry_date);

CREATE INDEX IF NOT EXISTS ix_claims_customer_id ON claims(customer_id);
CREATE INDEX IF NOT EXISTS ix_claims_policy_id ON claims(policy_id);
CREATE INDEX IF NOT EXISTS ix_claims_claim_date ON claims(claim_date);
CREATE INDEX IF NOT EXISTS ix_claims_jurisdiction ON claims(jurisdiction);
CREATE INDEX IF NOT EXISTS ix_claims_fraud_flag ON claims(fraud_flag);

CREATE INDEX IF NOT EXISTS ix_brokers_status ON brokers(status);
CREATE INDEX IF NOT EXISTS ix_brokers_email ON brokers(email);

CREATE INDEX IF NOT EXISTS ix_api_keys_broker_id ON api_keys(broker_id);
CREATE INDEX IF NOT EXISTS ix_api_keys_api_key_hash ON api_keys(api_key_hash);
