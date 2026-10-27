import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta

from celery import Celery, current_task

from backend.database import WorkerSessionFactory
from backend.log import correlation_id, new_correlation_id
from backend.mail import service as mail_service
from backend.mail.celery_app import celery_app
from backend.mail.config import mail_settings
from backend.mail.email import get_email_sender
from backend.mail.repository import SqlEmailOutboxRepository

logger = logging.getLogger(__name__)

_email_sender = get_email_sender()


def _seed_correlation_id() -> None:
    """Tie a task's log lines together under its Celery task id.

    Set before `asyncio.run`, so the coroutine's context copy carries it. Falls
    back to a fresh id when the task function is called outside a worker.
    """
    task_id = getattr(getattr(current_task, "request", None), "id", None)
    correlation_id.set(task_id or new_correlation_id())


async def _dispatch_email(entry_id: str) -> None:
    now = datetime.now(UTC)
    async with WorkerSessionFactory() as db, db.begin():
        outbox_repo = SqlEmailOutboxRepository(db)
        await mail_service.dispatch_email(
            outbox_repo,
            _email_sender,
            uuid.UUID(entry_id),
            now=now,
            max_attempts=mail_settings.EMAIL_MAX_DISPATCH_ATTEMPTS,
            sending_stale_before=now
            - timedelta(seconds=mail_settings.EMAIL_SWEEP_SENDING_STALE_AFTER_SECONDS),
        )


@celery_app.task(
    name="backend.mail.tasks.dispatch_email",
    autoretry_for=(Exception,),
    retry_backoff=120,
    retry_backoff_max=960,
    retry_jitter=False,
    max_retries=mail_settings.EMAIL_MAX_DISPATCH_ATTEMPTS - 1,
)
def dispatch_email(entry_id: str) -> None:
    """Celery task: dispatch one outbox entry's email.

    The row's `kind` picks the template and sender, so one task covers every
    email type. Celery retries a failure with exponential backoff, while the service counts
    `attempts` on the row and marks it `DEAD` at `EMAIL_MAX_DISPATCH_ATTEMPTS`.
    """
    _seed_correlation_id()
    asyncio.run(_dispatch_email(entry_id))


def broker_queue_depth(app: Celery) -> int:
    """Count the messages waiting in `app`'s default queue, not yet taken by a worker."""
    with app.connection_for_read() as conn:
        declared = conn.default_channel.queue_declare(queue=app.conf.task_default_queue)
    return declared.message_count


async def _sweep_pending_emails() -> list[str]:
    now = datetime.now(UTC)
    async with WorkerSessionFactory() as db, db.begin():
        outbox_repo = SqlEmailOutboxRepository(db)
        stale = await mail_service.list_stale_pending_emails(
            outbox_repo,
            unattempted_before=now
            - timedelta(seconds=mail_settings.EMAIL_SWEEP_STALE_AFTER_SECONDS),
            attempted_before=now
            - timedelta(seconds=mail_settings.EMAIL_SWEEP_RETRYING_STALE_AFTER_SECONDS),
            claimed_before=now
            - timedelta(seconds=mail_settings.EMAIL_SWEEP_SENDING_STALE_AFTER_SECONDS),
        )
        return [str(entry.id) for entry in stale]


@celery_app.task(name="backend.mail.tasks.sweep_pending_emails")
def sweep_pending_emails() -> None:
    """Celery beat task: re-dispatch outbox entries stuck `PENDING`.

    Runs every `EMAIL_SWEEP_INTERVAL_SECONDS`. Picks up never-attempted rows after
    `EMAIL_SWEEP_STALE_AFTER_SECONDS`, rows between retries only after
    `EMAIL_SWEEP_RETRYING_STALE_AFTER_SECONDS`, past the longest retry wait, and
    rows abandoned mid-send after `EMAIL_SWEEP_SENDING_STALE_AFTER_SECONDS`.

    A safety net, not the delivery path: the endpoints that enqueue email already
    queue dispatch directly. Skips the run while the broker queue holds dispatches:
    a stale row is then most likely still queued behind a backlog, and re-queueing
    every one each run would flood the broker with copies.
    """
    _seed_correlation_id()
    depth = broker_queue_depth(celery_app)
    if depth:
        logger.info("sweep skipped: %d dispatches still queued", depth)
        return
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
