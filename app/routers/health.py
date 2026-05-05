from datetime import datetime, timezone

from fastapi import APIRouter

from app.schemas import APIResponse
from app.services.scheduler import get_scheduler_status

router = APIRouter()


@router.get("/health")
def health_check() -> APIResponse:
    return APIResponse.ok({
        "service": "running",
        "scheduler_status": get_scheduler_status(),
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    })
