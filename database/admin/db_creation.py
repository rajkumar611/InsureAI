"""
Create and initialize the aus_underwriting database from scratch.
This is a standalone script that doesn't require SQLAlchemy models.
"""
import psycopg
import sys
from datetime import datetime

# Database connection parameters
DEFAULT_DB = "postgres"
TARGET_DB = "aus_underwriting"
POSTGRES_USER = "dbinsureai"
POSTGRES_PASSWORD = "125QueenStreet"  # Must match docker-compose.yml POSTGRES_PASSWORD
POSTGRES_HOST = "postgres.insureai.svc.cluster.local"
POSTGRES_PORT = 5432

def connect_to_db(db_name: str = DEFAULT_DB) -> psycopg.Connection:
    """Create a connection to PostgreSQL."""
    try:
        conn = psycopg.connect(
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
            dbname=db_name
        )
        return conn
    except Exception as e:
        print(f"❌ Failed to connect to {db_name}: {e}")
        sys.exit(1)

def create_database():
    """Drop and recreate the aus_underwriting database."""
    print("🔧 Dropping existing database (if any)...")
    conn = connect_to_db(DEFAULT_DB)
    conn.autocommit = True
    cursor = conn.cursor()

    try:
        # Terminate all connections to the database
        cursor.execute(f"""
            SELECT pg_terminate_backend(pg_stat_activity.pid)
            FROM pg_stat_activity
            WHERE pg_stat_activity.datname = '{TARGET_DB}'
            AND pid <> pg_backend_pid();
        """)

        # Drop the database
        cursor.execute(f"DROP DATABASE IF EXISTS {TARGET_DB}")
        print(f"✅ Dropped existing database (if any)")

        # Create fresh database
        cursor.execute(f"CREATE DATABASE {TARGET_DB}")
        print(f"✅ Created fresh database '{TARGET_DB}'")
    except Exception as e:
        print(f"❌ Error creating database: {e}")
        sys.exit(1)
    finally:
        cursor.close()
        conn.close()

def create_extensions(cursor):
    """Create required PostgreSQL extensions."""
    print("📦 Creating extensions...")
    try:
        cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
        # uuid-ossp not needed - gen_random_uuid() is built-in in PostgreSQL 13+
        print("✅ Extensions created")
    except Exception as e:
        print(f"❌ Error creating extensions: {e}")
        raise

def create_tables(cursor):
    """Create all database tables."""
    print("📋 Creating tables...")

    sql_statements = [
        # Brokers table
        """
        CREATE TABLE IF NOT EXISTS brokers (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name VARCHAR(128) UNIQUE NOT NULL,
            email VARCHAR(128) UNIQUE NOT NULL,
            organization VARCHAR(128),
            status VARCHAR(16) DEFAULT 'ACTIVE',
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # API Keys table
        """
        CREATE TABLE IF NOT EXISTS api_keys (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            broker_id UUID NOT NULL REFERENCES brokers(id) ON DELETE CASCADE,
            api_key_hash VARCHAR(255) UNIQUE NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            last_used_at TIMESTAMP WITH TIME ZONE
        )
        """,

        # Customers table
        """
        CREATE TABLE IF NOT EXISTS customers (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            customer_ref VARCHAR(64) UNIQUE NOT NULL,
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
            kyc_status VARCHAR(16) DEFAULT 'PENDING',
            kyc_verified_at TIMESTAMP WITH TIME ZONE,
            is_blacklisted BOOLEAN DEFAULT FALSE,
            blacklist_reason TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # Submissions table
        """
        CREATE TABLE IF NOT EXISTS submissions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            submission_ref VARCHAR(64) UNIQUE NOT NULL,
            broker_id VARCHAR(64),
            customer_id UUID,
            class_of_business VARCHAR(32),
            jurisdiction VARCHAR(8),
            status VARCHAR(32) DEFAULT 'RECEIVED',
            received_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            extracted_data JSONB,
            ingestion_confidence VARCHAR(16),
            ingestion_anomalies JSONB,
            missing_fields JSONB
        )
        """,

        # Workflows table
        """
        CREATE TABLE IF NOT EXISTS workflows (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            submission_id UUID UNIQUE NOT NULL REFERENCES submissions(id) ON DELETE CASCADE,
            policy_id VARCHAR(64) UNIQUE,
            status VARCHAR(32) DEFAULT 'STARTED',
            current_node VARCHAR(64),
            state_snapshot JSONB,
            error_log JSONB,
            loopback_counts JSONB,
            started_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP WITH TIME ZONE,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # Regulations table
        """
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
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # Policies table
        """
        CREATE TABLE IF NOT EXISTS policies (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            policy_number VARCHAR(64) UNIQUE NOT NULL,
            customer_id UUID NOT NULL REFERENCES customers(id),
            submission_id UUID REFERENCES submissions(id),
            workflow_id UUID,
            class_of_business VARCHAR(32) NOT NULL,
            jurisdiction VARCHAR(8) NOT NULL,
            status VARCHAR(16) DEFAULT 'ACTIVE',
            sum_insured NUMERIC(18, 2) NOT NULL,
            currency VARCHAR(8) NOT NULL,
            annual_premium NUMERIC(12, 2) NOT NULL,
            inception_date TIMESTAMP WITH TIME ZONE NOT NULL,
            expiry_date TIMESTAMP WITH TIME ZONE NOT NULL,
            policy_conditions JSONB,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # Claims table
        """
        CREATE TABLE IF NOT EXISTS claims (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            claim_number VARCHAR(64) UNIQUE NOT NULL,
            customer_id UUID NOT NULL REFERENCES customers(id),
            policy_id UUID REFERENCES policies(id),
            class_of_business VARCHAR(32) NOT NULL,
            jurisdiction VARCHAR(8) NOT NULL,
            risk_address_region VARCHAR(128),
            claim_date TIMESTAMP WITH TIME ZONE NOT NULL,
            date_reported TIMESTAMP WITH TIME ZONE NOT NULL,
            cause_of_loss VARCHAR(128) NOT NULL,
            incurred_amount NUMERIC(18, 2),
            reserved_amount NUMERIC(18, 2),
            currency VARCHAR(8) NOT NULL,
            status VARCHAR(16) DEFAULT 'SETTLED',
            is_large_loss BOOLEAN DEFAULT FALSE,
            fraud_flag BOOLEAN DEFAULT FALSE,
            fraud_investigation_status VARCHAR(32),
            claim_summary TEXT,
            settled_at TIMESTAMP WITH TIME ZONE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # Claims Embeddings table (for RAG with pgvector)
        """
        CREATE TABLE IF NOT EXISTS claims_embeddings (
            id BIGSERIAL PRIMARY KEY,
            customer_ref VARCHAR(64),
            customer_id UUID REFERENCES customers(id),
            claim_id UUID NOT NULL REFERENCES claims(id),
            risk_address_region VARCHAR(128),
            class_of_business VARCHAR(32) NOT NULL,
            jurisdiction VARCHAR(8) NOT NULL,
            claim_date TIMESTAMP WITH TIME ZONE,
            cause_of_loss VARCHAR(128),
            incurred_amount NUMERIC(18, 2),
            currency VARCHAR(8),
            is_large_loss BOOLEAN DEFAULT FALSE,
            fraud_flag BOOLEAN DEFAULT FALSE,
            claim_summary TEXT,
            embedding vector(384),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # Cost Ledger table
        """
        CREATE TABLE IF NOT EXISTS cost_ledger (
            id SERIAL PRIMARY KEY,
            submission_id UUID REFERENCES submissions(id),
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
            timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # Underwriter Queue table
        """
        CREATE TABLE IF NOT EXISTS underwriter_queue (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            workflow_id UUID UNIQUE NOT NULL,
            submission_id UUID NOT NULL REFERENCES submissions(id),
            policy_id VARCHAR(64),
            priority VARCHAR(16) DEFAULT 'STANDARD',
            sla_deadline TIMESTAMP WITH TIME ZONE NOT NULL,
            assigned_underwriter_id VARCHAR(64),
            locked_at TIMESTAMP WITH TIME ZONE,
            status VARCHAR(32) DEFAULT 'PENDING',
            risk_assessment_snapshot JSONB,
            decision JSONB,
            pipeline_state_snapshot JSONB,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP WITH TIME ZONE
        )
        """
    ]

    for i, sql in enumerate(sql_statements, 1):
        try:
            cursor.execute(sql)
            print(f"  ✅ Table {i}/{len(sql_statements)} created")
        except Exception as e:
            print(f"  ❌ Error creating table {i}: {e}")
            raise

def create_indexes(cursor):
    """Create indexes for performance."""
    print("🔍 Creating indexes...")

    # Standard indexes
    indexes = [
        ("submissions", "submission_ref", "ix_submissions_submission_ref"),
        ("submissions", "customer_id", "ix_submissions_customer_id"),
        ("submissions", "status", "ix_submissions_status"),
        ("workflows", "submission_id", "ix_workflows_submission_id"),
        ("workflows", "status", "ix_workflows_status"),
        ("cost_ledger", "policy_id", "ix_cost_ledger_policy_id"),
        ("cost_ledger", "agent_name", "ix_cost_ledger_agent_name"),
        ("cost_ledger", "timestamp", "ix_cost_ledger_timestamp"),
        ("cost_ledger", "submission_id", "ix_cost_ledger_submission_id"),
        ("claims_embeddings", "customer_ref", "ix_claims_embeddings_customer_ref"),
        ("claims_embeddings", "customer_id", "ix_claims_embeddings_customer_id"),
        ("claims_embeddings", "claim_id", "ix_claims_embeddings_claim_id"),
        ("underwriter_queue", "sla_deadline", "ix_underwriter_queue_sla_deadline"),
        ("customers", "jurisdiction", "ix_customers_jurisdiction"),
        ("customers", "kyc_status", "ix_customers_kyc_status"),
        ("policies", "customer_id", "ix_policies_customer_id"),
        ("policies", "status", "ix_policies_status"),
        ("policies", "expiry_date", "ix_policies_expiry_date"),
        ("claims", "customer_id", "ix_claims_customer_id"),
        ("claims", "policy_id", "ix_claims_policy_id"),
        ("claims", "claim_date", "ix_claims_claim_date"),
        ("claims", "jurisdiction", "ix_claims_jurisdiction"),
        ("claims", "fraud_flag", "ix_claims_fraud_flag"),
        ("brokers", "status", "ix_brokers_status"),
        ("brokers", "email", "ix_brokers_email"),
        ("api_keys", "broker_id", "ix_api_keys_broker_id"),
        ("api_keys", "api_key_hash", "ix_api_keys_api_key_hash"),
    ]

    for i, (table, column, index_name) in enumerate(indexes, 1):
        try:
            cursor.execute(f"CREATE INDEX IF NOT EXISTS {index_name} ON {table}({column})")
            print(f"  ✅ Index {i}/{len(indexes)} created: {index_name}")
        except Exception as e:
            print(f"  ⚠️  Index {index_name} error (may already exist): {e}")

    # Composite indexes
    composite_indexes = [
        ("regulations", "(jurisdiction, class_of_business, expiry_date)", "ix_regulations_active"),
        ("claims_embeddings", "(class_of_business, jurisdiction)", "ix_claims_embeddings_class_jurisdiction"),
        ("underwriter_queue", "(status, priority)", "ix_underwriter_queue_status_priority"),
    ]

    for i, (table, columns, index_name) in enumerate(composite_indexes, 1):
        try:
            cursor.execute(f"CREATE INDEX IF NOT EXISTS {index_name} ON {table}{columns}")
            print(f"  ✅ Composite index {i}/{len(composite_indexes)} created: {index_name}")
        except Exception as e:
            print(f"  ⚠️  Composite index {index_name} error (may already exist): {e}")

    # pgvector HNSW index for semantic search
    try:
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS ix_claims_embedding_vector ON claims_embeddings "
            "USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)"
        )
        print(f"  ✅ Vector index created: ix_claims_embedding_vector (pgvector HNSW)")
    except Exception as e:
        print(f"  ⚠️  Vector index error (may require pgvector extension): {e}")

def main():
    """Main execution."""
    print("\n" + "="*60)
    print("🗄️  Database Creation Script for aus_underwriting")
    print("="*60 + "\n")

    # Step 1: Create database
    create_database()

    # Step 2: Connect to new database and create schema
    print("\n🔌 Connecting to new database...")
    conn = connect_to_db(TARGET_DB)
    conn.autocommit = False
    cursor = conn.cursor()

    try:
        # Step 3: Create extensions
        create_extensions(cursor)

        # Step 4: Create tables
        create_tables(cursor)

        # Step 5: Create indexes
        create_indexes(cursor)

        # Commit all changes
        conn.commit()
        print("\n✅ All changes committed successfully!")

    except Exception as e:
        conn.rollback()
        print(f"\n❌ Error during schema creation: {e}")
        sys.exit(1)
    finally:
        cursor.close()
        conn.close()

    print("\n" + "="*60)
    print("✨ Database initialization complete!")
    print("="*60)
    print("\nNext steps:")
    print("1. Verify database: docker exec -it postgres_insureai psql -U dbinsureai -l | findstr aus_underwriting")
    print("2. Seed data: uv run python database/admin/seed_data.py")
    print("3. Seed brokers: uv run python database/admin/seed_brokers.py")
    print("4. Connect in DBeaver to localhost:5432/aus_underwriting\n")

if __name__ == "__main__":
    main()
