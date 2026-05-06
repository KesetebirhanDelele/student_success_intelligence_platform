import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas import APIResponse, ManualActionRequest
from app.services.outreach import execute_manual_action

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/actions/manual")
async def manual_action(
    body: ManualActionRequest,
    db: AsyncSession = Depends(get_db),
) -> APIResponse:
    result = await execute_manual_action(db, body.user_id, body.action_type, body.notes)

    if result.get("status") == "not_found":
        return APIResponse.fail("NOT_FOUND", f"No outreach record for student {body.user_id}")
    if result.get("status") == "invalid_transition":
        return APIResponse.fail(
            "INVALID_TRANSITION",
            f"Cannot transition {result['from']} → {result['to']}",
        )
    if result.get("status") == "invalid_action":
        return APIResponse.fail("INVALID_ACTION", f"Unknown action: {body.action_type}")

    return APIResponse.ok(result)
