from __future__ import annotations
from datetime import datetime
from uuid import uuid4, UUID
from enum import Enum, unique
from typing import Optional, List, Dict, Any
from sqlalchemy import String, MetaData, JSON, TIMESTAMP, Index, ForeignKey, Boolean
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB, ARRAY, UUID as PG_UUID
from sqlalchemy.sql import func
from src.core.security import encrypt_pii, decrypt_pii


# Enum definitions
@unique
class MessageStatus(str, Enum):
    QUEUED = "QUEUED"
    RETRY_PENDING = "RETRY_PENDING"
    SENT = "SENT"
    DELIVERED = "DELIVERED"
    BOUNCED = "BOUNCED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

# Base configuration
class Base(DeclarativeBase):
    pass


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    status: Mapped[MessageStatus] = mapped_column(String, index=True, default=MessageStatus.QUEUED)
    status_reason: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    provider_message_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    # Core mail fields
    subject: Mapped[str] = mapped_column(String, nullable=False)
    from_address: Mapped[str] = mapped_column(String, nullable=False)
    # Using JSONB for array or special PG types if using Postgres specifically, otherwise generic JSON/String
    to_addresses: Mapped[List[str]] = mapped_column(ARRAY(String), nullable=False)
    cc_addresses: Mapped[Optional[List[str]]] = mapped_column(ARRAY(String), nullable=True)
    bcc_addresses: Mapped[Optional[List[str]]] = mapped_column(ARRAY(String), nullable=True)

    # Content
    # Store encrypted PII or body. For PII minimization, we encrypt body and subject?
    # Spec says "PII minimization + payload encryption at rest". Let's assume body is sensitive.
    # We store it encrypted.
    encrypted_body: Mapped[str] = mapped_column(String, nullable=False)
    body_content_type: Mapped[str] = mapped_column(String, default="text/html")

    # Metadata
    campaign_id: Mapped[Optional[str]] = mapped_column(String, index=True, nullable=True)
    tags: Mapped[Optional[List[str]]] = mapped_column(ARRAY(String), nullable=True)
    metadata_fields: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    
    # Relationships
    outbox_entry: Mapped[Optional["Outbox"]] = relationship("Outbox", back_populates="message", uselist=False, cascade="all, delete-orphan")


class Outbox(Base):
    """
    Queue for messages waiting to be dispatched.
    Separated from Main Log for performance (smaller active table).
    """
    __tablename__ = "outbox"

    message_id: Mapped[UUID] = mapped_column(ForeignKey("messages.id"), primary_key=True)
    next_attempt_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), index=True, server_default=func.now())
    retry_count: Mapped[int] = mapped_column(default=0)
    last_attempt_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    locked_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    locked_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    message: Mapped["Message"] = relationship("Message", back_populates="outbox_entry")

    __table_args__ = (
        Index("ix_outbox_next_attempt", "next_attempt_at"),
    )


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    request_hash: Mapped[str] = mapped_column(String, nullable=False)
    response_status: Mapped[int] = mapped_column(nullable=False)
    response_body: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())

class DeadLetterQueue(Base):
    __tablename__ = "dead_letter_queue"
    
    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    message_id: Mapped[UUID] = mapped_column(ForeignKey("messages.id"), nullable=False)
    reason: Mapped[str] = mapped_column(String, nullable=False)
    failed_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())
    payload_snapshot: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)


class ProviderEvent(Base):
    __tablename__ = "provider_events"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    provider: Mapped[str] = mapped_column(String, nullable=False)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False)
    received_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())
