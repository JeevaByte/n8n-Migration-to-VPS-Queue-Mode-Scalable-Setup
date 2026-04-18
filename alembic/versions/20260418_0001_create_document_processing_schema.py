"""create document processing schema

Revision ID: 20260418_0001
Revises:
Create Date: 2026-04-18 18:10:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260418_0001"
down_revision = None
branch_labels = None
depends_on = None


document_status = sa.Enum(
    "uploaded", "processing", "completed", "failed", name="document_status"
)


def upgrade() -> None:
    bind = op.get_bind()
    document_status.create(bind, checkfirst=True)

    op.create_table(
        "documents",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("file_path", sa.String(length=1024), nullable=False),
        sa.Column("status", document_status, nullable=False, server_default="uploaded"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processing_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processing_failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("error_details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("ocr_output", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_index("ix_documents_status", "documents", ["status"], unique=False)
    op.create_index("ix_documents_created_at", "documents", ["created_at"], unique=False)
    op.create_index("ix_documents_updated_at", "documents", ["updated_at"], unique=False)
    op.create_index(
        "ix_documents_processing_started_at", "documents", ["processing_started_at"], unique=False
    )
    op.create_index(
        "ix_documents_processing_completed_at",
        "documents",
        ["processing_completed_at"],
        unique=False,
    )
    op.execute(
        """
        CREATE FUNCTION set_documents_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_documents_updated_at
        BEFORE UPDATE ON documents
        FOR EACH ROW
        EXECUTE FUNCTION set_documents_updated_at();
        """
    )

    op.create_table(
        "transactions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("vendor", sa.String(length=255), nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("category", sa.String(length=120), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.CheckConstraint("amount >= 0", name="ck_transactions_amount_non_negative"),
    )
    op.create_index("ix_transactions_document_id", "transactions", ["document_id"], unique=False)
    op.create_index("ix_transactions_vendor", "transactions", ["vendor"], unique=False)
    op.create_index("ix_transactions_date", "transactions", ["date"], unique=False)
    op.create_index("ix_transactions_category", "transactions", ["category"], unique=False)
    op.create_index(
        "ix_transactions_document_date",
        "transactions",
        ["document_id", "date"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_transactions_document_date", table_name="transactions")
    op.drop_index("ix_transactions_category", table_name="transactions")
    op.drop_index("ix_transactions_date", table_name="transactions")
    op.drop_index("ix_transactions_vendor", table_name="transactions")
    op.drop_index("ix_transactions_document_id", table_name="transactions")
    op.drop_table("transactions")

    op.drop_index("ix_documents_created_at", table_name="documents")
    op.drop_index("ix_documents_status", table_name="documents")
    op.drop_index("ix_documents_processing_completed_at", table_name="documents")
    op.drop_index("ix_documents_processing_started_at", table_name="documents")
    op.drop_index("ix_documents_updated_at", table_name="documents")
    op.execute("DROP TRIGGER IF EXISTS trg_documents_updated_at ON documents")
    op.execute("DROP FUNCTION IF EXISTS set_documents_updated_at")
    op.drop_table("documents")

    bind = op.get_bind()
    document_status.drop(bind, checkfirst=True)
