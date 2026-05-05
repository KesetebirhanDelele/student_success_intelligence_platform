import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import APIResponse, TriggerOutreachRequest, VALID_CHECKPOINTS
from app.services.outreach import run_outreach_batch

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/outreach/trigger")
def trigger_outreach(
    body: TriggerOutreachRequest,
    db: Session = Depends(get_db),
) -> APIResponse:
    if not body.validate_checkpoint():
        raise HTTPException(
            status_code=422,
            detail={"code": "INVALID_INPUT", "message": f"checkpoint_type must be one of {VALID_CHECKPOINTS}"},
        )

    results = run_outreach_batch(db, body.checkpoint_type)
    return APIResponse.ok({"triggered": True, "summary": results})
