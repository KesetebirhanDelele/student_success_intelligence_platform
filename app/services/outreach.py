import logging
from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.models import StudentTriggerData, StudentOutreachTracking
from app.state_machine import validate_transition, StateViolationError
from app.services.eligibility import check_eligibility
from app.services.decision_engine import decide
from app.services import ghl

logger = logging.getLogger(__name__)


# ── Batch outreach run ────────────────────────────────────────────────────────

def run_outreach_batch(db: Session, checkpoint_type: str) -> dict:
    """
    Full daily outreach cycle for a given checkpoint.
    Returns a summary dict with counts.
    """
    logger.info("Starting outreach batch | scope=%s | checkpoint=%s", settings.SYSTEM_SCOPE, checkpoint_type)
    now = datetime.utcnow()
    results = {"processed": 0, "triggered": 0, "skipped": 0, "errors": 0}

    students: List[StudentTriggerData] = (
        db.query(StudentTriggerData).all()
    )

    processed = 0
    for student in students:
        if processed >= settings.concurrency_limit:
            logger.warning("Concurrency limit (%d) reached — stopping batch", settings.concurrency_limit)
            break

        try:
            _process_student(db, student, checkpoint_type, now, results)
            processed += 1
        except Exception as exc:
            logger.error("Unexpected error processing student %d: %s", student.UserID, exc)
            results["errors"] += 1

    logger.info("Outreach batch complete | %s", results)
    return results


def _process_student(
    db: Session,
    student: StudentTriggerData,
    checkpoint_type: str,
    now: datetime,
    results: dict,
) -> None:
    results["processed"] += 1

    # Load latest outreach record for this student + checkpoint
    record: Optional[StudentOutreachTracking] = (
        db.query(StudentOutreachTracking)
        .filter_by(UserID=student.UserID, CheckpointType=checkpoint_type)
        .order_by(StudentOutreachTracking.ContactAttempt.desc())
        .first()
    )

    current_state = record.State if record else None
    last_contact_time = record.ContactDate if record else None
    contact_attempt = record.ContactAttempt if record else 0
    call_connected = record.CallConnected if record else False
    meeting_booked = record.MeetingBooked if record else False

    # Eligibility check
    eligibility = check_eligibility(
        user_id=student.UserID,
        checkpoint_type=checkpoint_type,
        hws_behind=student.HWsBehind or 0,
        avg_eff_rating=student.AvgEffRating or 0.0,
        last_activity_days=student.LastActivityDays or 0,
        email=student.Email,
        phone_number=student.PhoneNumber,
        last_contact_time=last_contact_time,
        contact_attempt=contact_attempt,
        state=current_state,
        current_time=now,
    )

    if not eligibility.eligible:
        logger.debug(
            "Student %d ineligible: %s", student.UserID, eligibility.reason_codes
        )
        results["skipped"] += 1
        return

    # Decision engine
    decision = decide(
        user_id=student.UserID,
        contact_attempt=contact_attempt,
        last_contact_time=last_contact_time,
        call_connected=call_connected,
        meeting_booked=meeting_booked,
        ipbc_enrolled=False,  # sourced from IPBCInterest in future
        hws_behind=student.HWsBehind or 0,
        avg_eff_rating=student.AvgEffRating or 0.0,
        last_activity_days=student.LastActivityDays or 0,
        current_time=now,
    )

    if decision.action_type in ("NO_ACTION", "CLOSE_CASE"):
        _upsert_state(db, record, student, checkpoint_type, "CLOSED" if decision.action_type == "CLOSE_CASE" else current_state, now)
        results["skipped"] += 1
        return

    if decision.action_type in ("TRIGGER_OUTREACH", "RETRY_OUTREACH"):
        _execute_outreach(db, record, student, checkpoint_type, decision, eligibility, now, results)


def _execute_outreach(
    db: Session,
    record: Optional[StudentOutreachTracking],
    student: StudentTriggerData,
    checkpoint_type: str,
    decision,
    eligibility,
    now: datetime,
    results: dict,
) -> None:
    # Idempotency: ensure no duplicate trigger for same attempt
    new_attempt = (record.ContactAttempt if record else 0) + (1 if record else 0)
    # For first outreach (no existing record) attempt = 1
    if record is None:
        new_attempt = 1

    existing = (
        db.query(StudentOutreachTracking)
        .filter_by(
            UserID=student.UserID,
            CheckpointType=checkpoint_type,
            ContactAttempt=new_attempt,
        )
        .first()
    )
    if existing:
        logger.warning(
            "Duplicate trigger blocked for student %d attempt %d", student.UserID, new_attempt
        )
        results["skipped"] += 1
        return

    # GHL trigger — only when state = QUEUED (enforced by creating QUEUED record first)
    queued = StudentOutreachTracking(
        UserID=student.UserID,
        CheckpointType=checkpoint_type,
        State="QUEUED",
        ContactDate=now,
        ContactAttempt=new_attempt,
        CreatedAt=now,
        UpdatedAt=now,
    )
    db.add(queued)
    db.flush()  # get OutreachID before GHL call

    success = ghl.trigger_outreach(
        user_id=student.UserID,
        first_name=student.FirstName or "",
        last_name=student.LastName or "",
        email=student.Email,
        phone_number=student.PhoneNumber,
        checkpoint_type=checkpoint_type,
        hws_behind=student.HWsBehind or 0,
        avg_eff_rating=student.AvgEffRating or 0.0,
        last_activity_days=student.LastActivityDays or 0,
        contact_attempt=new_attempt,
        priority=eligibility.priority,
        reason_codes=decision.reason_codes,
    )

    if success:
        queued.State = "CONTACTED"
        queued.UpdatedAt = datetime.utcnow()
        db.commit()
        results["triggered"] += 1
        logger.info("Student %d contacted (attempt %d)", student.UserID, new_attempt)
    else:
        queued.State = "ELIGIBLE"  # roll back to eligible for manual retry
        queued.UpdatedAt = datetime.utcnow()
        db.commit()
        results["errors"] += 1
        logger.error("GHL trigger failed for student %d", student.UserID)


def _upsert_state(
    db: Session,
    record: Optional[StudentOutreachTracking],
    student: StudentTriggerData,
    checkpoint_type: str,
    new_state: Optional[str],
    now: datetime,
) -> None:
    if record and new_state and record.State != new_state:
        try:
            validate_transition(record.State, new_state)
            record.State = new_state
            record.UpdatedAt = now
            db.commit()
        except StateViolationError as exc:
            logger.error("State violation for student %d: %s", student.UserID, exc)


# ── Manual action ─────────────────────────────────────────────────────────────

def execute_manual_action(db: Session, user_id: int, action_type: str) -> bool:
    """Executes a manual operator action. Returns True on success."""
    record: Optional[StudentOutreachTracking] = (
        db.query(StudentOutreachTracking)
        .filter_by(UserID=user_id)
        .order_by(StudentOutreachTracking.ContactAttempt.desc())
        .first()
    )

    now = datetime.utcnow()

    if action_type == "CLOSE_CASE":
        if record:
            try:
                validate_transition(record.State, "CLOSED")
                record.State = "CLOSED"
                record.UpdatedAt = now
                db.commit()
                return True
            except StateViolationError as exc:
                logger.error("Manual CLOSE_CASE violation for user %d: %s", user_id, exc)
                return False
        return False

    if action_type == "BOOK_MEETING":
        if record:
            try:
                validate_transition(record.State, "MEETING_SCHEDULED")
                record.State = "MEETING_SCHEDULED"
                record.MeetingBooked = True
                record.UpdatedAt = now
                db.commit()
                return True
            except StateViolationError as exc:
                logger.error("Manual BOOK_MEETING violation for user %d: %s", user_id, exc)
                return False
        return False

    # TRIGGER_OUTREACH and RETRY handled via batch trigger (out of scope for direct manual call here)
    logger.warning("Manual action %s not directly handled — use /outreach/trigger", action_type)
    return False
