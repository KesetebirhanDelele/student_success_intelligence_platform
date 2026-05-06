from __future__ import annotations

import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import settings

logger = logging.getLogger(__name__)

_scheduler = AsyncIOScheduler()
CHECKPOINTS = ["SQL", "SSRS", "SSIS", "POST_COMPLETION"]


async def _run_all_checkpoints() -> None:
    from app.database import AsyncSessionLocal
    from app.services.outreach import run_outreach_batch

    logger.info("Scheduled batch starting | mode=%s", settings.EXECUTION_MODE)
    async with AsyncSessionLocal() as db:
        for checkpoint in CHECKPOINTS:
            try:
                summary = await run_outreach_batch(db, checkpoint)
                logger.info("Checkpoint %s: %s", checkpoint, summary)
            except Exception as exc:
                logger.error("Checkpoint %s failed: %s", checkpoint, exc, exc_info=True)
    logger.info("Scheduled batch complete")


def start_scheduler() -> None:
    _scheduler.add_job(
        _run_all_checkpoints,
        CronTrigger(
            hour=settings.SCHEDULER_HOUR,
            minute=settings.SCHEDULER_MINUTE,
            timezone=settings.SCHEDULER_TIMEZONE,
        ),
        id="daily_outreach",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    _scheduler.start()
    logger.info(
        "Scheduler started | daily at %02d:%02d %s",
        settings.SCHEDULER_HOUR,
        settings.SCHEDULER_MINUTE,
        settings.SCHEDULER_TIMEZONE,
    )


def stop_scheduler() -> None:
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")


def get_scheduler_status() -> str:
    return "active" if _scheduler.running else "stopped"
