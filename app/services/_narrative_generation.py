"""
Monthly narrative generation — one LLM call per student, all 5 types at once.

Narrative types (mirror _NARRATIVE_TYPES in snapshot.py):
  risk_summary, progress_summary, monthly_narrative,
  intervention_recommendation, sentiment_analysis

Governance:
  AP-AI10  — no raw PII (name, phone, email, transcript) in prompts or logs
  FAD-1    — finalized insights are immutable; existing finalized rows not overwritten
  AP-LF8   — idempotency: each student+type pair generated at most once per run
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

_NARRATIVE_TYPES = [
    "risk_summary",
    "progress_summary",
    "monthly_narrative",
    "intervention_recommendation",
    "sentiment_analysis",
]

_SYSTEM_PROMPT = (
    "You are a student success intelligence advisor. Analyze the student performance "
    "data provided and return a JSON object with exactly these 5 string keys:\n"
    "- risk_summary: 1-2 sentence risk assessment covering academic, financial, and engagement signals\n"
    "- progress_summary: 1-2 sentence summary of current academic progress and trajectory\n"
    "- monthly_narrative: 2-3 sentence comprehensive narrative of the student's overall status\n"
    "- intervention_recommendation: 1-2 sentence specific, actionable recommendation for the advisor\n"
    "- sentiment_analysis: Exactly one of POSITIVE, NEUTRAL, AT_RISK, or CRITICAL followed "
    "by a colon and a one-sentence rationale (e.g. 'AT_RISK: Student has not logged in for 14 days.')\n\n"
    "Base your analysis strictly on the provided numeric and categorical data. "
    "Return only valid JSON with these 5 string keys."
)

_USER_TEMPLATE = """\
Program: {PathName}
Section: {section}
Attendance: {attendance}%
HWs behind: {hw_behind}
Efficiency rating: {eff_rating}/5
Days since last activity: {last_activity}
Days since last login: {last_login}
Recent 10-day logins: {recent_logins}
Payment balance owed: ${payment_balance}
Fee paid: {fee_paid}
Active status: {active_status}
Status I: {status_i}
Status II: {status_ii}"""


def _build_context(student: dict) -> str:
    return _USER_TEMPLATE.format(
        PathName=student.get("PathName") or "Unknown",
        section=student.get("section") or "Unknown",
        attendance=student.get("AttendancePercentage") or 0,
        hw_behind=student.get("p_HWsBehind") or 0,
        eff_rating=round(float(student.get("p_AvgEffRating") or 0.0), 1),
        last_activity=student.get("p_LastActivityDays") or 0,
        last_login=student.get("p_LastLoginDays") or 0,
        recent_logins=student.get("Past10DaysLogon") or 0,
        payment_balance=student.get("PaymentBalance") or 0,
        fee_paid="Yes" if student.get("FeePaid") else "No",
        active_status=student.get("ActiveStatus") or "Unknown",
        status_i=student.get("StatusI") or "",
        status_ii=student.get("StatusII") or "",
    )


async def generate_student_narratives(
    user_id: int,
    student: dict,
    db: Any,
    *,
    model: str,
    api_key: str,
) -> dict:
    """
    Generate all 5 monthly narrative types for one student in a single LLM call.
    Skips types already finalized for this student (FAD-1 / AP-LF8).
    Returns {"generated": [types], "skipped": [types], "error": str|None}
    """
    from sqlalchemy import select
    from app.models import AIInsight

    # Check which types are already finalized — don't overwrite them (FAD-1)
    already_finalized = set(
        (await db.execute(
            select(AIInsight.insight_type)
            .where(AIInsight.user_id == user_id)
            .where(AIInsight.is_finalized == True)  # noqa: E712
            .where(AIInsight.insight_type.in_(_NARRATIVE_TYPES))
        )).scalars().all()
    )

    needed = [t for t in _NARRATIVE_TYPES if t not in already_finalized]
    if not needed:
        return {"generated": [], "skipped": list(already_finalized), "error": None}

    # One LLM call for all 5 types
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=api_key)
        resp = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": _build_context(student)},
            ],
            response_format={"type": "json_object"},
            max_tokens=600,
            timeout=30,
        )
        narratives: dict = json.loads(resp.choices[0].message.content or "{}")
    except Exception as exc:
        return {"generated": [], "skipped": list(already_finalized), "error": f"{type(exc).__name__}: {exc}"}

    now = datetime.now(timezone.utc)
    generated = []
    for insight_type in needed:
        content = narratives.get(insight_type)
        if not content:
            continue
        db.add(AIInsight(
            user_id=user_id,
            insight_type=insight_type,
            content_text=str(content),
            model_used=model,
            is_finalized=True,
            finalized_at=now,
            execution_mode="SHADOW",
            governance_scope="SHADOW_ONLY",
            execution_type="original",
            is_replay=False,
            correlation_id=str(uuid.uuid4()),
            origin_source="generate_monthly_narratives",
            origin_authority="narrative_generation_service",
        ))
        generated.append(insight_type)

    if generated:
        await db.commit()

    return {"generated": generated, "skipped": list(already_finalized), "error": None}


async def generate_all_monthly_narratives(db: Any) -> dict:
    """
    Batch-generate monthly narratives for all active students.
    Idempotent: skips students where all 5 types are already finalized.
    Logs progress every 25 students.

    Returns summary counts plus up to 10 error samples.
    """
    from sqlalchemy import select
    from app.config import settings
    from app.models import StudentTriggerData

    api_key = settings.LLM_API_KEY
    model = settings.LLM_MODEL

    if not api_key:
        return {"status": "error", "error": "LLM_API_KEY not configured in .env"}

    rows = (await db.execute(select(StudentTriggerData))).scalars().all()
    total = len(rows)
    new_count = skipped_count = failed_count = 0
    errors: list = []

    for i, row in enumerate(rows, 1):
        student = {c.key: getattr(row, c.key) for c in row.__table__.columns}
        user_id = student["UserID"]

        result = await generate_student_narratives(
            user_id=user_id,
            student=student,
            db=db,
            model=model,
            api_key=api_key,
        )

        if result["error"]:
            failed_count += 1
            if len(errors) < 10:
                errors.append({"user_id": user_id, "error": result["error"]})
        elif result["generated"]:
            new_count += 1
        else:
            skipped_count += 1

        if i % 25 == 0 or i == total:
            logger.info(json.dumps({
                "event": "narrative_generation_progress",
                "processed": i,
                "total": total,
                "new": new_count,
                "skipped": skipped_count,
                "failed": failed_count,
            }))

    return {
        "status": "ok",
        "total_students": total,
        "students_with_new_narratives": new_count,
        "students_already_finalized": skipped_count,
        "students_failed": failed_count,
        "model": model,
        "errors": errors,
    }
