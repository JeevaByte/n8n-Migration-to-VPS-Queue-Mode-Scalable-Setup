"""SQLAlchemy models for the document processing schema."""

from __future__ import annotations

import enum
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for ORM models."""


class DocumentStatus(str, enum.Enum):
    """Allowed processing states for a document."""

    UPLOADED = "uploaded"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class Document(Base):
    """Uploaded source document to be processed."""

    __tablename__ = "documents"
    __table_args__ = (
        Index("ix_documents_status", "status"),
        Index("ix_documents_created_at", "created_at"),
        Index("ix_documents_updated_at", "updated_at"),
        Index("ix_documents_processing_started_at", "processing_started_at"),
        Index("ix_documents_processing_completed_at", "processing_completed_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus, name="document_status", native_enum=True, validate_strings=True),
        nullable=False,
        default=DocumentStatus.UPLOADED,
        server_default=DocumentStatus.UPLOADED.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    processing_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    processing_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    processing_failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    ocr_output: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    transactions: Mapped[list["Transaction"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )


class Transaction(Base):
    """Extracted transaction entry linked to a document."""

    __tablename__ = "transactions"
    __table_args__ = (
        Index("ix_transactions_document_id", "document_id"),
        Index("ix_transactions_vendor", "vendor"),
        Index("ix_transactions_date", "date"),
        Index("ix_transactions_category", "category"),
        Index("ix_transactions_document_date", "document_id", "date"),
        CheckConstraint("amount >= 0", name="ck_transactions_amount_non_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    vendor: Mapped[str] = mapped_column(String(255), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    category: Mapped[str | None] = mapped_column(String(120), nullable=True)
    transaction_metadata: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    document: Mapped[Document] = relationship(back_populates="transactions")
