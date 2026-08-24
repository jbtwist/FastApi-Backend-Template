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
