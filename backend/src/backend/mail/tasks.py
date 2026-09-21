import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta

from backend.database import WorkerSessionFactory
from backend.mail import service as mail_service
from backend.mail.celery_app import celery_app
from backend.mail.config import mail_settings
from backend.mail.email import get_email_sender
from backend.mail.repository import SqlEmailOutboxRepository

logger = logging.getLogger(__name__)

_email_sender = get_email_sender()


async def _dispatch_email(entry_id: str) -> None:
    async with WorkerSessionFactory() as db, db.begin():
        outbox_repo = SqlEmailOutboxRepository(db)
        await mail_service.dispatch_email(
            outbox_repo,
            _email_sender,
            uuid.UUID(entry_id),
            now=datetime.now(UTC),
            max_attempts=mail_settings.EMAIL_MAX_DISPATCH_ATTEMPTS,
        )


@celery_app.task(
    name="backend.mail.tasks.dispatch_email",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    max_retries=5,
)
def dispatch_email(entry_id: str) -> None:
    """Celery task: dispatch one outbox entry's email.

    The row's `kind` picks the template and sender, so one task covers every
    email type. Two retry layers apply: Celery retries this task with backoff
    for a transient failure, while the service counts `attempts` on the row
    itself and marks it `DEAD` at `EMAIL_MAX_DISPATCH_ATTEMPTS`.
    """
    asyncio.run(_dispatch_email(entry_id))


async def _sweep_pending_emails() -> list[str]:
    cutoff = datetime.now(UTC) - timedelta(seconds=mail_settings.EMAIL_SWEEP_STALE_AFTER_SECONDS)
    async with WorkerSessionFactory() as db, db.begin():
        outbox_repo = SqlEmailOutboxRepository(db)
        stale = await mail_service.list_stale_pending_emails(outbox_repo, older_than=cutoff)
        return [str(entry.id) for entry in stale]


@celery_app.task(name="backend.mail.tasks.sweep_pending_emails")
def sweep_pending_emails() -> None:
    """Celery beat task: re-dispatch outbox entries stuck `PENDING`.

    Runs every `EMAIL_SWEEP_INTERVAL_SECONDS`, over rows untouched for
    `EMAIL_SWEEP_STALE_AFTER_SECONDS`.

    A safety net, not the delivery path: the endpoints that enqueue email already
    queue dispatch directly.
    """
    for entry_id in asyncio.run(_sweep_pending_emails()):
        dispatch_email.delay(entry_id)


async def queue_dispatch_email(entry_id: str) -> None:
    """Fire the Celery dispatch for a freshly queued outbox row, tolerating a broker outage.

    A failed enqueue must not surface to the caller: on `forgot-password` a 500
    for registered addresses, against a 204 for unknown ones, would be an
    enumeration oracle. The row stays `PENDING` and the sweep redelivers it.
    """
    try:
        await asyncio.to_thread(dispatch_email.delay, entry_id)
    except Exception:
        logger.warning("dispatch enqueue failed for outbox entry %s", entry_id, exc_info=True)
