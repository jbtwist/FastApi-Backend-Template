from celery import Celery

from backend.mail.config import mail_settings

celery_app = Celery(
    "mail",
    broker=mail_settings.CELERY_BROKER_URL,
    backend=mail_settings.CELERY_RESULT_BACKEND,
    include=["backend.mail.tasks"],
)
celery_app.conf.timezone = "UTC"
