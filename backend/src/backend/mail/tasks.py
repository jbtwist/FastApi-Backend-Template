import asyncio
import uuid
from datetime import UTC, datetime, timedelta

from backend.database import WorkerSessionFactory
from backend.mail import service as mail_service
from backend.mail.celery_app import celery_app
from backend.mail.config import mail_settings
from backend.mail.email import get_email_sender
from backend.mail.repository import SqlEmailOutboxRepository

_email_sender = get_email_sender()


async def _dispatch_verification_email(entry_id: str) -> None:
    async with WorkerSessionFactory() as db, db.begin():
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


async def _sweep_pending_emails() -> list[str]:
    cutoff = datetime.now(UTC) - timedelta(seconds=mail_settings.SWEEP_STALE_AFTER_SECONDS)
    async with WorkerSessionFactory() as db, db.begin():
        outbox_repo = SqlEmailOutboxRepository(db)
        stale = await mail_service.list_stale_pending_emails(outbox_repo, older_than=cutoff)
        return [str(entry.id) for entry in stale]


@celery_app.task(name="backend.mail.tasks.sweep_pending_emails")
def sweep_pending_emails() -> None:
    for entry_id in asyncio.run(_sweep_pending_emails()):
        dispatch_verification_email.delay(entry_id)
