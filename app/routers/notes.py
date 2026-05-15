"""Student notes router — manual and AI-generated notes with timestamps."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import StudentNote
from app.schemas import APIResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/notes")


class NoteCreateRequest(BaseModel):
    user_id: int
    content: str
    author: str = "operator"
    is_ai_generated: bool = False


@router.post("")
async def create_note(
    req: NoteCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    """Add an internal note for a student."""
    if not req.content.strip():
        return APIResponse.fail("EMPTY_NOTE", "Note content cannot be empty.")

    note = StudentNote(
        user_id=req.user_id,
        author=req.author[:100],
        content=req.content[:4000],
        is_ai_generated=req.is_ai_generated,
    )
    db.add(note)
    await db.commit()
    logger.info("Note created user_id=%s author=%s ai=%s", req.user_id, req.author, req.is_ai_generated)

    return APIResponse.ok({
        "id": note.id,
        "user_id": note.user_id,
        "author": note.author,
        "is_ai_generated": note.is_ai_generated,
        "created_at": note.created_at.isoformat() if note.created_at else None,
    })


@router.get("/{user_id}")
async def list_notes(user_id: int, db: AsyncSession = Depends(get_db)) -> APIResponse:
    """All notes for a student, newest first."""
    result = await db.execute(
        select(StudentNote)
        .where(StudentNote.user_id == user_id)
        .order_by(StudentNote.created_at.desc())
    )
    notes = result.scalars().all()
    return APIResponse.ok({
        "user_id": user_id,
        "count": len(notes),
        "notes": [
            {
                "id": n.id,
                "author": n.author,
                "content": n.content,
                "is_ai_generated": n.is_ai_generated,
                "created_at": n.created_at.isoformat() if n.created_at else None,
            }
            for n in notes
        ],
    })
