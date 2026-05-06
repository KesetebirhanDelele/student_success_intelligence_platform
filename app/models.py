from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Index, Integer,
    String, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


# ── Source mirror (populated from SQL Server sync) ─────────────────────────────

class StudentTriggerData(Base):
    """Local mirror of AI_ChatBot_TriggerData. Populated by SQL Server sync."""
    __tablename__ = "ai_chatbot_triggerdata"

    UserID: Mapped[int] = mapped_column(Integer, primary_key=True)
    FirstName: Mapped[Optional[str]] = mapped_column(String(100))
    LastName: Mapped[Optional[str]] = mapped_column(String(100))
    Email: Mapped[Optional[str]] = mapped_column(String(255))
    PhoneNumber: Mapped[Optional[str]] = mapped_column(String(50))
    PathName: Mapped[Optional[str]] = mapped_column(String(100))
    HWsBehind: Mapped[int] = mapped_column(Integer, default=0)
    AvgEffRating: Mapped[float] = mapped_column(default=0.0)
    LastActivityDays: Mapped[int] = mapped_column(Integer, default=0)


# ── System tables (PostgreSQL source of truth) ────────────────────────────────

class StudentOutreachTracking(Base):
    """Current outreach state per student + checkpoint."""
    __tablename__ = "student_outreach_tracking"
    __table_args__ = (
        UniqueConstraint("user_id", "checkpoint_type", name="uq_student_checkpoint"),
        Index("ix_sot_state", "state"),
        Index("ix_sot_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    checkpoint_type: Mapped[str] = mapped_column(String(50), nullable=False)
    state: Mapped[str] = mapped_column(String(50), nullable=False, default="ELIGIBLE")
    current_attempt: Mapped[int] = mapped_column(Integer, default=0)
    last_contact_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    next_retry_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    history: Mapped[list[OutreachHistory]] = relationship(
        "OutreachHistory", back_populates="tracking", cascade="all, delete-orphan"
    )
    transitions: Mapped[list[StateTransitionLog]] = relationship(
        "StateTransitionLog", back_populates="tracking", cascade="all, delete-orphan"
    )


class OutreachHistory(Base):
    """Full record of every outreach attempt — payload, response, LLM output."""
    __tablename__ = "outreach_history"
    __table_args__ = (
        Index("ix_oh_user_id", "user_id"),
        Index("ix_oh_tracking_id", "tracking_id"),
        Index("ix_oh_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tracking_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("student_outreach_tracking.id"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    checkpoint_type: Mapped[str] = mapped_column(String(50), nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    channel: Mapped[Optional[str]] = mapped_column(String(20))       # CALL | SMS | EMAIL
    action: Mapped[Optional[str]] = mapped_column(String(50))        # CALL_SIMULATED | SMS_SIMULATED …
    execution_mode: Mapped[str] = mapped_column(String(10), default="SHADOW")
    simulated_status: Mapped[str] = mapped_column(String(20), default="NOT_SENT")
    payload: Mapped[Optional[dict]] = mapped_column(JSONB)           # full outreach payload
    response_payload: Mapped[Optional[dict]] = mapped_column(JSONB)  # webhook / API response
    llm_analysis: Mapped[Optional[dict]] = mapped_column(JSONB)      # LLM structured output
    decision: Mapped[Optional[str]] = mapped_column(String(50))
    state_before: Mapped[Optional[str]] = mapped_column(String(50))
    state_after: Mapped[Optional[str]] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    tracking: Mapped[StudentOutreachTracking] = relationship(
        "StudentOutreachTracking", back_populates="history"
    )


class StateTransitionLog(Base):
    """Immutable audit trail of every state change."""
    __tablename__ = "state_transition_log"
    __table_args__ = (
        Index("ix_stl_tracking_id", "tracking_id"),
        Index("ix_stl_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tracking_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("student_outreach_tracking.id"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    from_state: Mapped[str] = mapped_column(String(50), nullable=False)
    to_state: Mapped[str] = mapped_column(String(50), nullable=False)
    trigger: Mapped[str] = mapped_column(String(100))
    actor: Mapped[str] = mapped_column(String(50), default="system")  # system | manual | webhook
    meta: Mapped[Optional[dict]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    tracking: Mapped[StudentOutreachTracking] = relationship(
        "StudentOutreachTracking", back_populates="transitions"
    )


class ProcessedEvents(Base):
    """Idempotency store — prevents duplicate webhook/event processing."""
    __tablename__ = "processed_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    event_type: Mapped[Optional[str]] = mapped_column(String(50))
    user_id: Mapped[Optional[int]] = mapped_column(Integer)
    raw_payload: Mapped[Optional[dict]] = mapped_column(JSONB)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
