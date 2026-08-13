"""Scheduled deadline-reminder task — see PHASE_13_NOTIFICATIONS.md.

Unlike every other task in this codebase, this one is periodic (Celery
beat, see app/worker/celery_app.py's beat_schedule), not triggered by a
single user action -- there's no per-call idempotent "claim" to make
since it's not tied to one document/roadmap/etc.; NotificationService's
own dedup (keyed on reference_id) is what makes running this on a timer
safe rather than needing task-level idempotency of its own.
"""

from celery.utils.log import get_task_logger

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.services.notification_reminders import NotificationReminderService
from app.worker.celery_app import NOTIFICATIONS_QUEUE, celery_app

logger = get_task_logger(__name__)
settings = get_settings()


@celery_app.task(name="notifications.send_task_reminders", queue=NOTIFICATIONS_QUEUE)
def send_task_reminders() -> dict:
    db = SessionLocal()
    try:
        service = NotificationReminderService(db, settings)
        result = service.send_task_reminders()
        logger.info("send_task_reminders completed", extra=result)
        return result
    finally:
        db.close()
