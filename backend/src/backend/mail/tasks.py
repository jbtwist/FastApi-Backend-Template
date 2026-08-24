import asyncio
import uuid
from datetime import UTC, datetime

from backend.database import SessionFactory
from backend.mail import service as mail_service
from backend.mail.celery_app import celery_app
from backend.mail.config import mail_settings
from backend.mail.email import LoggingEmailSender
from backend.mail.repository import SqlEmailOutboxRepository

_email_sender = LoggingEmailSender()


async def _dispatch_verification_email(entry_id: str) -> None:
    async with SessionFactory() as db, db.begin():
        outbox_repo = SqlEmailOutboxRepository(db)
        await mail_service.dispatch_verification_email(
            outbox_repo,
            _email_sender,
            uuid.UUID(entry_id),
            now=datetime.now(UTC),
            max_attempts=mail_settings.MAX_DISPATCH_ATTEMPTS,
        )


@celery_app.task(
    name="backend.mail.tasks.dispatch_verification_email",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    max_retries=5,
)
def dispatch_verification_email(entry_id: str) -> None:
    asyncio.run(_dispatch_verification_email(entry_id))
