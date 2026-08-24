from datetime import timedelta

from celery import Celery

from backend.mail.config import mail_settings

celery_app = Celery(
    "mail",
    broker=mail_settings.CELERY_BROKER_URL,
    backend=mail_settings.CELERY_RESULT_BACKEND,
    include=["backend.mail.tasks"],
)
celery_app.conf.timezone = "UTC"
celery_app.conf.beat_schedule = {
    "sweep-pending-emails": {
        "task": "backend.mail.tasks.sweep_pending_emails",
        "schedule": timedelta(seconds=mail_settings.SWEEP_INTERVAL_SECONDS),
    },
}
