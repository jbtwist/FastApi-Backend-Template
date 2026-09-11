import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.log import log_event
from backend.mail.models import EmailKind, EmailOutboxEntry, EmailOutboxStatus


class SqlEmailOutboxRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(
        self,
        *,
        user_id: uuid.UUID,
        email: str,
        token: str,
        created_at: datetime,
        kind: EmailKind = EmailKind.VERIFICATION,
    ) -> EmailOutboxEntry:
        entry = EmailOutboxEntry(
            user_id=user_id,
            email=email,
            token=token,
            kind=kind,
            status=EmailOutboxStatus.PENDING,
        )
        self._db.add(entry)
        await self._db.flush()
        log_event(
            "db_write",
            table=EmailOutboxEntry.__tablename__,
            operation="insert",
            entry_id=entry.id,
            user_id=user_id,
            kind=kind,
        )
        return entry

    async def get_by_id(self, entry_id: uuid.UUID) -> EmailOutboxEntry | None:
        return await self._db.get(EmailOutboxEntry, entry_id)

    async def mark_sent(self, entry_id: uuid.UUID, *, sent_at: datetime) -> bool:
        entry = await self._db.get(EmailOutboxEntry, entry_id)
        if entry is None or entry.status != EmailOutboxStatus.PENDING:
            return False
        entry.status = EmailOutboxStatus.SENT
        entry.sent_at = sent_at
        await self._db.flush()
        log_event(
            "db_write",
            table=EmailOutboxEntry.__tablename__,
            operation="update",
            column="status",
            entry_id=entry_id,
            status=EmailOutboxStatus.SENT,
        )
        return True

    async def mark_attempt_failed(
        self, entry_id: uuid.UUID, *, attempted_at: datetime
    ) -> EmailOutboxEntry:
        entry = await self._db.get(EmailOutboxEntry, entry_id)
        entry.attempts += 1
        entry.last_attempted_at = attempted_at
        await self._db.flush()
        log_event(
            "db_write",
            table=EmailOutboxEntry.__tablename__,
            operation="update",
            column="attempts",
            entry_id=entry_id,
            attempts=entry.attempts,
        )
        return entry

    async def mark_dead(self, entry_id: uuid.UUID, *, failed_at: datetime) -> bool:
        entry = await self._db.get(EmailOutboxEntry, entry_id)
        if entry is None:
            return False
        entry.status = EmailOutboxStatus.DEAD
        entry.dead_at = failed_at
        await self._db.flush()
        log_event(
            "db_write",
            table=EmailOutboxEntry.__tablename__,
            operation="update",
            column="status",
            entry_id=entry_id,
            status=EmailOutboxStatus.DEAD,
            attempts=entry.attempts,
        )
        return True

    async def list_stale_pending(self, *, older_than: datetime) -> list[EmailOutboxEntry]:
        last_activity_at = func.coalesce(
            EmailOutboxEntry.last_attempted_at, EmailOutboxEntry.created_at
        )
        result = await self._db.execute(
            select(EmailOutboxEntry).where(
                EmailOutboxEntry.status == EmailOutboxStatus.PENDING,
                last_activity_at <= older_than,
            )
        )
        return list(result.scalars())
