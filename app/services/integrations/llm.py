"""LLM transcript analysis — active in both SHADOW and LIVE modes."""
from __future__ import annotations

import json
import logging

from app.config import settings

logger = logging.getLogger(__name__)

_ANALYSIS_PROMPT = """\
You are analyzing a student outreach interaction transcript.

Student ID: {user_id}
Attempt: {attempt}
Checkpoint: {checkpoint}

Transcript:
{transcript}

Respond with a JSON object only (no markdown, no commentary):
{{
  "sentiment": "positive|neutral|negative",
  "intent": "schedule_meeting|needs_support|not_interested|unclear",
  "recommended_action": "BOOK_MEETING|RETRY_OUTREACH|ESCALATE|CLOSE",
  "summary": "<one sentence>",
  "confidence": 0.0
}}"""


async def analyze_transcript(
    transcript: str,
    user_id: int,
    attempt: int,
    checkpoint: str = "",
) -> dict:
    if not settings.LLM_API_KEY:
        logger.warning("LLM_API_KEY not set — skipping transcript analysis")
        return {"status": "skipped", "reason": "LLM_NOT_CONFIGURED"}

    try:
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=settings.LLM_API_KEY)
        prompt = _ANALYSIS_PROMPT.format(
            user_id=user_id,
            attempt=attempt,
            checkpoint=checkpoint,
            transcript=transcript,
        )
        message = await client.messages.create(
            model=settings.LLM_MODEL,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text.strip()
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(raw[start:end])
        return {"status": "parse_error", "raw": raw}
    except Exception as exc:
        logger.error("LLM analysis failed for user %s: %s", user_id, exc)
        return {"status": "error", "reason": str(exc)}
