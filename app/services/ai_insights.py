"""AI insight generation — cached 24 h in PostgreSQL, shadow-safe (no outbound comm)."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from openai import AsyncOpenAI
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import AIInsight

logger = logging.getLogger(__name__)

INSIGHT_TYPES = frozenset({
    "OUTREACH_DRAFT",
    "INTERVENTION",
    "RISK_EXPLANATION",
    "INTERVIEW_COACHING",
})

_CACHE_HOURS = 24


def _student_context(student: dict) -> str:
    name = f"{student.get('FirstName', '')} {student.get('LastName', '')}".strip() or f"#{student.get('UserID')}"
    section = student.get("CurrentSection") or student.get("PathName") or "Unknown"
    return (
        f"Student: {name} | Section: {section} | "
        f"HWs Behind: {student.get('HWsBehind', 0)} | "
        f"Avg Efficiency: {float(student.get('AvgEffRating') or 0):.1f} | "
        f"Inactive Days: {student.get('LastActivityDays', 0)} | "
        f"Attendance: {float(student.get('AttendancePercentage') or 0):.1f}% | "
        f"Past 10-Day Logins: {student.get('Past10DaysLogon', 0)}"
    )


def _build_prompt(insight_type: str, student: dict) -> str:
    ctx = _student_context(student)
    prompts = {
        "OUTREACH_DRAFT": (
            "You are a student success coordinator. Write a brief, warm, professional "
            "outreach message to re-engage this student. Under 100 words. "
            "Do NOT use placeholders.\n\nContext: " + ctx
        ),
        "INTERVENTION": (
            "You are a student success analyst. Recommend one specific intervention action "
            "with a 1-sentence rationale. Be direct and actionable.\n\nContext: " + ctx
        ),
        "RISK_EXPLANATION": (
            "Explain in 2-3 sentences why this student is at risk of not completing their "
            "program, citing specific data points.\n\nContext: " + ctx
        ),
        "INTERVIEW_COACHING": (
            "Provide 2 specific interview coaching suggestions based on this student's "
            "current academic performance. Be practical.\n\nContext: " + ctx
        ),
    }
    return prompts[insight_type]


async def get_or_generate(
    user_id: int,
    insight_type: str,
    student: dict,
    db: AsyncSession,
) -> dict:
    """Return cached insight if valid, otherwise generate and persist a new one."""
    if insight_type not in INSIGHT_TYPES:
        return {"error": f"Unknown insight_type '{insight_type}'. Valid: {sorted(INSIGHT_TYPES)}"}

    if not settings.LLM_API_KEY:
        return {
            "insight_type": insight_type,
            "content": "AI insights unavailable — LLM_API_KEY not configured in .env.",
            "cached": False,
            "model": None,
        }

    now = datetime.now(tz=timezone.utc)

    # Cache check
    cached_q = await db.execute(
        select(AIInsight)
        .where(
            AIInsight.user_id == user_id,
            AIInsight.insight_type == insight_type,
            or_(AIInsight.expires_at.is_(None), AIInsight.expires_at > now),
        )
        .order_by(AIInsight.created_at.desc())
        .limit(1)
    )
    cached = cached_q.scalar_one_or_none()
    if cached:
        return {
            "insight_type": insight_type,
            "content": cached.content_text,
            "cached": True,
            "model": cached.model_used,
            "created_at": cached.created_at.isoformat(),
        }

    # Generate
    prompt = _build_prompt(insight_type, student)
    try:
        client = AsyncOpenAI(api_key=settings.LLM_API_KEY)
        resp = await client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400,
            temperature=0.7,
        )
        content = resp.choices[0].message.content or ""
    except Exception as exc:
        logger.error(
            "AI insight generation failed user=%s type=%s error_class=%s msg=%s",
            user_id, insight_type, type(exc).__name__, exc,
        )
        return {
            "insight_type": insight_type,
            "content": f"Generation failed: {exc}",
            "cached": False,
            "model": None,
        }

    insight = AIInsight(
        user_id=user_id,
        insight_type=insight_type,
        content_text=content,
        model_used=settings.LLM_MODEL,
        expires_at=now + timedelta(hours=_CACHE_HOURS),
    )
    db.add(insight)
    await db.commit()
    logger.info("AI insight generated user=%s type=%s model=%s", user_id, insight_type, settings.LLM_MODEL)

    return {
        "insight_type": insight_type,
        "content": content,
        "cached": False,
        "model": settings.LLM_MODEL,
        "created_at": now.isoformat(),
    }
