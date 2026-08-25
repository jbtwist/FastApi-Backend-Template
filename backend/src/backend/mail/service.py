"""Email outbox: durable queueing and dispatch of outbound email."""

import uuid
from datetime import datetime
from typing import Protocol

from backend.mail.exceptions import EmailOutboxEntryNotFound
from backend.mail.models import EmailOutboxEntry, EmailOutboxStatus

DEFAULT_MAX_DISPATCH_ATTEMPTS = 5


class EmailSender(Protocol):
    async def send_verification_email(self, *, email: str, token: str) -> None: ...


class EmailOutboxRepository(Protocol):
    async def create(
        self, *, user_id: uuid.UUID, email: str, token: str, created_at: datetime
    ) -> EmailOutboxEntry: ...
    async def get_by_id(self, entry_id: uuid.UUID) -> EmailOutboxEntry | None: ...
    async def mark_sent(self, entry_id: uuid.UUID, *, sent_at: datetime) -> bool: ...
    async def mark_attempt_failed(
        self, entry_id: uuid.UUID, *, attempted_at: datetime
    ) -> EmailOutboxEntry: ...
    async def mark_dead(self, entry_id: uuid.UUID, *, failed_at: datetime) -> bool: ...
    async def list_stale_pending(self, *, older_than: datetime) -> list[EmailOutboxEntry]: ...


async def enqueue_email(
    outbox_repo: EmailOutboxRepository,
    *,
    user_id: uuid.UUID,
    email: str,
    token: str,
    created_at: datetime,
) -> EmailOutboxEntry:
    """Write a pending outbox row without contacting the email provider.

    This is the durability boundary: the row exists whether or not the Celery
    dispatch that follows ever runs, so a caller that writes this in the same
    DB transaction as the triggering action (e.g. registration) can't lose the
    email to a Celery/Redis outage — `sweep_pending_emails` will eventually
    pick up anything left `PENDING` too long.
    """
    return await outbox_repo.create(
        user_id=user_id, email=email, token=token, created_at=created_at
    )


async def dispatch_verification_email(
    outbox_repo: EmailOutboxRepository,
    email_sender: EmailSender,
    entry_id: uuid.UUID,
    *,
    now: datetime,
    max_attempts: int = DEFAULT_MAX_DISPATCH_ATTEMPTS,
) -> None:
    """Send one outbox entry's verification email and update its status.

    No-ops if the entry is already `SENT` or `DEAD` — safe to call more than
    once for the same entry (the Celery task retries and the sweep can both
    target it). On send failure, increments `attempts` and re-raises so the
    Celery task's own retry/backoff applies; once `attempts` reaches
    `max_attempts` the entry is marked `DEAD` and given up on for good.

    Raises:
        EmailOutboxEntryNotFound: no entry with this id exists.
    """
    entry = await outbox_repo.get_by_id(entry_id)
    if entry is None:
        raise EmailOutboxEntryNotFound

    if entry.status != EmailOutboxStatus.PENDING:
        return

    try:
        await email_sender.send_verification_email(email=entry.email, token=entry.token)
    except Exception:
        updated = await outbox_repo.mark_attempt_failed(entry_id, attempted_at=now)
        if updated.attempts >= max_attempts:
            await outbox_repo.mark_dead(entry_id, failed_at=now)
        raise

    await outbox_repo.mark_sent(entry_id, sent_at=now)


async def list_stale_pending_emails(
    outbox_repo: EmailOutboxRepository, *, older_than: datetime
) -> list[EmailOutboxEntry]:
    """List `PENDING` entries with no activity since `older_than`.

    Catches entries whose dispatch was never actually queued (e.g. the
    process crashed between the outbox write and the Celery `.delay()` call)
    as well as ones stuck between retries — "activity" is the entry's
    `last_attempted_at`, falling back to `created_at` if it's never been
    attempted.
    """
    return await outbox_repo.list_stale_pending(older_than=older_than)
