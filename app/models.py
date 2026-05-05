from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Text, UniqueConstraint, Index
)

from app.database import Base


class StudentTriggerData(Base):
    """AI_ChatBot_TriggerData — external read-only student source."""
    __tablename__ = "AI_ChatBot_TriggerData"

    UserID = Column(Integer, primary_key=True)
    FirstName = Column(String(100))
    LastName = Column(String(100))
    Email = Column(String(255))
    PhoneNumber = Column(String(50))
    PathName = Column(String(100))
    HWsBehind = Column(Integer, default=0)
    AvgEffRating = Column(Float)
    LastActivityDays = Column(Integer, default=0)


class StudentOutreachTracking(Base):
    """System-owned outreach lifecycle table."""
    __tablename__ = "StudentOutreachTracking"

    OutreachID = Column(Integer, primary_key=True, autoincrement=True)
    UserID = Column(Integer, nullable=False)
    CheckpointType = Column(String(50), nullable=False)
    State = Column(String(50), nullable=False, default="ELIGIBLE")
    ContactDate = Column(DateTime, nullable=True)
    ContactAttempt = Column(Integer, default=0)
    CallConnected = Column(Boolean, default=False)
    CallDuration = Column(Integer, default=0)
    Transcript = Column(Text, nullable=True)
    Sentiment = Column(String(50), nullable=True)
    MeetingBooked = Column(Boolean, default=False)
    IPBCInterest = Column(String(50), nullable=True)
    CreatedAt = Column(DateTime, default=datetime.utcnow)
    UpdatedAt = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("UserID", "CheckpointType", "ContactAttempt", name="uix_outreach_unique"),
        Index("ix_sot_userid", "UserID"),
        Index("ix_sot_state", "State"),
        Index("ix_sot_contactdate", "ContactDate"),
        Index("ix_sot_checkpoint", "CheckpointType"),
    )
