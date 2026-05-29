"""resize embedding vector from 1536 to 384 (sentence-transformers)

Revision ID: 0002
Revises: 0001
Create Date: 2024-11-02
"""
from __future__ import annotations

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_claims_embedding_vector")
    op.execute("""
        ALTER TABLE claims_embeddings
        ALTER COLUMN embedding TYPE vector(384)
        USING embedding::text::vector(384)
    """)
    op.execute("""
        CREATE INDEX ix_claims_embedding_vector
        ON claims_embeddings
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_claims_embedding_vector")
    op.execute("""
        ALTER TABLE claims_embeddings
        ALTER COLUMN embedding TYPE vector(1536)
        USING embedding::text::vector(1536)
    """)
    op.execute("""
        CREATE INDEX ix_claims_embedding_vector
        ON claims_embeddings
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
    """)
