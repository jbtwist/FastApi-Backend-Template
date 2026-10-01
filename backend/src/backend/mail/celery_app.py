from datetime import timedelta

from celery import Celery
from celery.signals import setup_logging

from backend import models  # noqa: F401
from backend.config import settings
from backend.log import configure_logging
from backend.mail.config import mail_settings


@setup_logging.connect
def _configure_worker_logging(**_kwargs: object) -> None:
    """Give the worker the same stdout formatting the API uses.

    Celery hijacks the root logger on worker startup and would otherwise replace
    the handler installed here, so every event emitted from a task would lose its
    format. Connecting any receiver to `setup_logging` tells Celery to configure
    nothing and leave logging to the app.
    """
    configure_logging(level=settings.LOG_LEVEL, log_format=settings.LOG_FORMAT)


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
        "schedule": timedelta(seconds=mail_settings.EMAIL_SWEEP_INTERVAL_SECONDS),
    },
}
