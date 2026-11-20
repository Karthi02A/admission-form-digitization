from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.analytics.database import Base


class Visitor(Base):
    __tablename__ = "analytics_visitors"

    visitor_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    sessions: Mapped[list["UserSession"]] = relationship(back_populates="visitor")


class UserSession(Base):
    __tablename__ = "analytics_sessions"

    session_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    visitor_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("analytics_visitors.visitor_id", ondelete="CASCADE"), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    active_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    visitor: Mapped[Visitor] = relationship(back_populates="sessions")

    __table_args__ = (
        Index("ix_analytics_sessions_started_at", "started_at"),
        Index("ix_analytics_sessions_visitor_id", "visitor_id"),
        Index("ix_analytics_sessions_last_activity_at", "last_activity_at"),
    )


class DocumentUsage(Base):
    """One row per document upload attempt, with its extraction outcome."""

    __tablename__ = "analytics_document_usage"

    usage_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    document_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True)
    batch_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    visitor_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    file_type: Mapped[str] = mapped_column(String(20), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    upload_status: Mapped[str] = mapped_column(String(20), nullable=False)
    extraction_status: Mapped[str] = mapped_column(String(20), nullable=False, default="not_started")
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    extracted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    extraction_duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    __table_args__ = (
        Index("ix_analytics_document_usage_uploaded_at", "uploaded_at"),
        Index("ix_analytics_document_usage_extraction_status", "extraction_status"),
    )
