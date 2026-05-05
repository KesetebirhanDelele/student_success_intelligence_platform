from datetime import datetime
from typing import Any, Optional, List
from pydantic import BaseModel


# ── Generic response wrapper ──────────────────────────────────────────────────

class APIResponse(BaseModel):
    status: str  # "success" | "error"
    data: Optional[Any] = None
    error: Optional[dict] = None

    @classmethod
    def ok(cls, data: Any = None) -> "APIResponse":
        return cls(status="success", data=data, error=None)

    @classmethod
    def fail(cls, code: str, message: str) -> "APIResponse":
        return cls(status="error", data=None, error={"code": code, "message": message})


# ── Outreach trigger ──────────────────────────────────────────────────────────

class CheckpointType(str):
    SQL = "SQL"
    SSRS = "SSRS"
    SSIS = "SSIS"
    POST_COMPLETION = "POST_COMPLETION"

VALID_CHECKPOINTS = {"SQL", "SSRS", "SSIS", "POST_COMPLETION"}


class TriggerOutreachRequest(BaseModel):
    checkpoint_type: str

    def validate_checkpoint(self) -> bool:
        return self.checkpoint_type in VALID_CHECKPOINTS


# ── Manual action ─────────────────────────────────────────────────────────────

VALID_ACTION_TYPES = {"TRIGGER_OUTREACH", "RETRY", "CLOSE_CASE", "BOOK_MEETING"}


class ManualActionRequest(BaseModel):
    user_id: int
    action_type: str

    def validate_action(self) -> bool:
        return self.action_type in VALID_ACTION_TYPES


# ── GHL webhook ───────────────────────────────────────────────────────────────

VALID_GHL_EVENTS = {"CALL_COMPLETED", "SMS_RESPONSE", "EMAIL_RESPONSE", "TRANSCRIPT_READY"}


class GHLWebhookPayload(BaseModel):
    user_id: int
    event_type: str
    call_connected: Optional[bool] = None
    call_duration: Optional[int] = None
    transcript: Optional[str] = None


# ── Student detail ────────────────────────────────────────────────────────────

class OutreachHistoryItem(BaseModel):
    outreach_id: int
    checkpoint_type: str
    state: str
    contact_date: Optional[datetime]
    contact_attempt: int
    call_connected: bool
    meeting_booked: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class StudentDetailData(BaseModel):
    user_id: int
    state: Optional[str]
    attempt_count: int
    history: List[OutreachHistoryItem]


# ── Metrics ───────────────────────────────────────────────────────────────────

class MetricsData(BaseModel):
    total_outreach: int
    contacted: int
    responded: int
    no_response: int
    meeting_booked: int
    closed: int
    success_rate: float
    meeting_rate: float
