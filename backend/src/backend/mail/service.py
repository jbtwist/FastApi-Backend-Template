"""Email outbox: durable queueing and dispatch of outbound email."""

import uuid
from datetime import datetime
from typing import Protocol

from backend.mail.exceptions import EmailOutboxEntryNotFound
from backend.mail.models import EmailKind, EmailOutboxEntry, EmailOutboxStatus

DEFAULT_MAX_DISPATCH_ATTEMPTS = 5


class EmailSender(Protocol):
    async def send_verification_email(self, *, email: str, token: str) -> None: ...
    async def send_password_reset_email(self, *, email: str, token: str) -> None: ...
    async def send_oauth_link_email(self, *, email: str, token: str) -> None: ...


class EmailOutboxRepository(Protocol):
    async def create(
        self,
        *,
        user_id: uuid.UUID,
        email: str,
        token: str,
        created_at: datetime,
        kind: EmailKind = EmailKind.VERIFICATION,
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
    kind: EmailKind = EmailKind.VERIFICATION,
) -> EmailOutboxEntry:
    """Write a pending outbox row without contacting the email provider.

    The durability boundary: written in the same transaction as the triggering
    action, the row survives a Celery or Redis outage, and
    `sweep_pending_emails` picks up whatever stays `PENDING` too long.
    """
    return await outbox_repo.create(
        user_id=user_id, email=email, token=token, created_at=created_at, kind=kind
    )


async def _send_for_kind(email_sender: EmailSender, entry: EmailOutboxEntry) -> None:
    """The single switch point wiring an `EmailKind` to a sender method.

    A new kind needs a branch here, a `render_*` template, and a `send_*` method
    on `EmailSender`.
    """
    if entry.kind == EmailKind.PASSWORD_RESET:
        await email_sender.send_password_reset_email(email=entry.email, token=entry.token)
    elif entry.kind == EmailKind.OAUTH_LINK:
        await email_sender.send_oauth_link_email(email=entry.email, token=entry.token)
    else:
        await email_sender.send_verification_email(email=entry.email, token=entry.token)


async def dispatch_email(
    outbox_repo: EmailOutboxRepository,
    email_sender: EmailSender,
    entry_id: uuid.UUID,
    *,
    now: datetime,
    max_attempts: int = DEFAULT_MAX_DISPATCH_ATTEMPTS,
) -> None:
    """Send one outbox entry's email and update its status.

    No-ops if the entry is already `SENT` or `DEAD`, so it is safe to call twice.
    A send failure increments `attempts` and re-raises, so the Celery task's
    backoff applies; at `max_attempts` the entry is marked `DEAD` for good.

    Raises:
        EmailOutboxEntryNotFound: no entry with this id exists.
    """
    entry = await outbox_repo.get_by_id(entry_id)
    if entry is None:
        raise EmailOutboxEntryNotFound

    if entry.status != EmailOutboxStatus.PENDING:
        return

    try:
        await _send_for_kind(email_sender, entry)
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

    Activity is `last_attempted_at`, falling back to `created_at`, so this
    catches entries whose dispatch was never queued as well as ones stuck
    between retries.
    """
    return await outbox_repo.list_stale_pending(older_than=older_than)
