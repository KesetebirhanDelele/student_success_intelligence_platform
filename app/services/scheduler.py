import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import settings

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def _daily_outreach_job() -> None:
    """Daily outreach job — runs all active checkpoints."""
    from app.database import SessionLocal
    from app.services.outreach import run_outreach_batch

    checkpoints = ["SQL", "SSRS", "SSIS", "POST_COMPLETION"]
    db = SessionLocal()
    try:
        for checkpoint in checkpoints:
            try:
                run_outreach_batch(db, checkpoint)
            except Exception as exc:
                logger.error("Batch failed for checkpoint %s: %s", checkpoint, exc)
    finally:
        db.close()


def start_scheduler() -> None:
    global _scheduler
    if not settings.SCHEDULER_ENABLED:
        logger.info("Scheduler disabled by config")
        return

    _scheduler = BackgroundScheduler(timezone=settings.SCHEDULER_TIMEZONE)
    _scheduler.add_job(
        _daily_outreach_job,
        trigger=CronTrigger(
            hour=settings.SCHEDULER_HOUR,
            minute=settings.SCHEDULER_MINUTE,
            timezone=settings.SCHEDULER_TIMEZONE,
        ),
        id="daily_outreach",
        name="Daily student outreach batch",
        replace_existing=True,
        misfire_grace_time=3600,  # allow up to 1h late run
    )
    _scheduler.start()
    logger.info(
        "Scheduler started — daily job at %02d:%02d %s",
        settings.SCHEDULER_HOUR,
        settings.SCHEDULER_MINUTE,
        settings.SCHEDULER_TIMEZONE,
    )


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")


def get_scheduler_status() -> str:
    if _scheduler is None:
        return "disabled"
    return "active" if _scheduler.running else "stopped"
