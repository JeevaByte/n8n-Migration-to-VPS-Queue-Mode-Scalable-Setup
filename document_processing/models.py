"""SQLAlchemy models for the document processing schema."""

from __future__ import annotations

import enum
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Index, Numeric, String, func
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
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    vendor: Mapped[str] = mapped_column(String(255), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    category: Mapped[str | None] = mapped_column(String(120), nullable=True)

    document: Mapped[Document] = relationship(back_populates="transactions")

