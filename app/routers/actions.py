import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import APIResponse, ManualActionRequest, VALID_ACTION_TYPES
from app.services.outreach import execute_manual_action

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/actions/manual")
def manual_action(
    body: ManualActionRequest,
    db: Session = Depends(get_db),
) -> APIResponse:
    if not body.validate_action():
        raise HTTPException(
            status_code=422,
            detail={"code": "INVALID_INPUT", "message": f"action_type must be one of {VALID_ACTION_TYPES}"},
        )

    success = execute_manual_action(db, body.user_id, body.action_type)
    if not success:
        raise HTTPException(
            status_code=400,
            detail={"code": "STATE_VIOLATION", "message": "Action could not be executed in current state"},
        )

    return APIResponse.ok({"executed": True})
