from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, field_validator

VALID_ACTION_TYPES = {"CLOSE_CASE", "BOOK_MEETING", "FORCE_RETRY", "ESCALATE"}
VALID_GHL_EVENTS = {"CALL_COMPLETED", "SMS_RESPONSE", "EMAIL_RESPONSE", "TRANSCRIPT_READY"}


class APIResponse(BaseModel):
    status: str
    data: Optional[Any] = None
    error: Optional[dict] = None
    meta: Optional[dict] = None

    @classmethod
    def ok(cls, data: Any = None, meta: Optional[dict] = None) -> "APIResponse":
        return cls(status="success", data=data, error=None, meta=meta)

    @classmethod
    def fail(cls, code: str, message: str, meta: Optional[dict] = None) -> "APIResponse":
        return cls(status="error", data=None, error={"code": code, "message": message}, meta=meta)


class TriggerOutreachRequest(BaseModel):
    checkpoint_type: str
    limit: int = 50


class ManualActionRequest(BaseModel):
    user_id: int
    action_type: str
    notes: Optional[str] = None

    @field_validator("action_type")
    @classmethod
    def validate_action(cls, v: str) -> str:
        if v not in VALID_ACTION_TYPES:
            raise ValueError(f"action_type must be one of {VALID_ACTION_TYPES}")
        return v


class GHLWebhookPayload(BaseModel):
    event_type: str
    user_id: Optional[int] = None
    contact_id: Optional[str] = None
    outcome: Optional[str] = None
    transcript: Optional[str] = None
    metadata: Optional[dict] = None


class OutreachHistoryItem(BaseModel):
    id: int
    attempt_number: int
    channel: Optional[str]
    action: Optional[str]
    execution_mode: str
    simulated_status: str
    decision: Optional[str]
    state_before: Optional[str]
    state_after: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class StudentDetailData(BaseModel):
    user_id: int
    checkpoint_type: str
    state: str
    current_attempt: int
    last_contact_at: Optional[datetime]
    next_retry_at: Optional[datetime]
    history: list[OutreachHistoryItem]
