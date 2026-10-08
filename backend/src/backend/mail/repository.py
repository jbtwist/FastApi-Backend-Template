import uuid
from datetime import datetime

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.log import audit_logger
from backend.mail.models import EmailKind, EmailOutboxEntry, EmailOutboxStatus

audit = audit_logger("db")


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
            created_at=created_at,
        )
        self._db.add(entry)
        await self._db.flush()
        audit.info(
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

    async def claim_for_send(
        self,
        entry_id: uuid.UUID,
        *,
        now: datetime,
        sending_stale_before: datetime | None = None,
    ) -> EmailOutboxEntry | None:
        """Take ownership of a `pending` entry, or `None` if another worker has it.

        One conditional `UPDATE`, so two workers racing the same row cannot both
        win it and send the email twice. A `sending` entry claimed before
        `sending_stale_before` is treated as abandoned and taken over.
        """
        claimable = EmailOutboxEntry.status == EmailOutboxStatus.PENDING
        if sending_stale_before is not None:
            claimable = or_(
                claimable,
                and_(
                    EmailOutboxEntry.status == EmailOutboxStatus.SENDING,
                    EmailOutboxEntry.last_attempted_at <= sending_stale_before,
                ),
            )
        result = await self._db.execute(
            update(EmailOutboxEntry)
            .where(EmailOutboxEntry.id == entry_id, claimable)
            .values(status=EmailOutboxStatus.SENDING, last_attempted_at=now)
            .returning(EmailOutboxEntry)
            .execution_options(synchronize_session="fetch"),
        )
        entry = result.scalar_one_or_none()
        if entry is None:
            return None
        audit.info(
            "db_write",
            table=EmailOutboxEntry.__tablename__,
            operation="update",
            column="status",
            entry_id=entry_id,
            status=EmailOutboxStatus.SENDING,
        )
        return entry

    async def mark_sent(self, entry_id: uuid.UUID, *, sent_at: datetime) -> bool:
        entry = await self._db.get(EmailOutboxEntry, entry_id)
        if entry is None or entry.status not in (
            EmailOutboxStatus.PENDING,
            EmailOutboxStatus.SENDING,
        ):
            return False
        entry.status = EmailOutboxStatus.SENT
        entry.sent_at = sent_at
        await self._db.flush()
        audit.info(
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
        """Count a failed attempt, releasing the claim so the retry can take it.

        Back to `pending` rather than left `sending`, so a retry does not have
        to wait out `EMAIL_SWEEP_SENDING_STALE_AFTER_SECONDS` first.
        """
        entry = await self._db.get(EmailOutboxEntry, entry_id)
        entry.attempts += 1
        entry.last_attempted_at = attempted_at
        if entry.status == EmailOutboxStatus.SENDING:
            entry.status = EmailOutboxStatus.PENDING
        await self._db.flush()
        audit.info(
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
        audit.info(
            "db_write",
            table=EmailOutboxEntry.__tablename__,
            operation="update",
            column="status",
            entry_id=entry_id,
            status=EmailOutboxStatus.DEAD,
            attempts=entry.attempts,
        )
        return True

    async def list_stale_pending(
        self,
        *,
        unattempted_before: datetime,
        attempted_before: datetime,
        claimed_before: datetime | None = None,
    ) -> list[EmailOutboxEntry]:
        stale_pending = and_(
            EmailOutboxEntry.status == EmailOutboxStatus.PENDING,
            or_(
                and_(
                    EmailOutboxEntry.attempts == 0,
                    EmailOutboxEntry.created_at <= unattempted_before,
                ),
                and_(
                    EmailOutboxEntry.attempts > 0,
                    EmailOutboxEntry.last_attempted_at <= attempted_before,
                ),
            ),
        )
        clauses = [stale_pending]
        if claimed_before is not None:
            clauses.append(
                and_(
                    EmailOutboxEntry.status == EmailOutboxStatus.SENDING,
                    EmailOutboxEntry.last_attempted_at <= claimed_before,
                )
            )
        result = await self._db.execute(select(EmailOutboxEntry).where(or_(*clauses)))
        return list(result.scalars())
