"""Persistence for `security_event` rows.

The write runs on the request's session, so a row lands in the same transaction
as the change it records: an event never outlives a rolled-back password reset,
and a committed reset always has its event.

`delete_before` deletes at most `batch_size` rows per call, leaving the caller to
loop. A single DELETE over a retention window's worth of rows holds a long
transaction, leaves the table full of dead tuples and hands autovacuum a spike
right after. Bounding the statement only helps if each one commits, so the
transaction boundary belongs to the caller, not here.
"""

import uuid
from datetime import datetime
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from backend.audit.models import SecurityEvent, SecurityEventKind


class SecurityEventRepository(Protocol):
    async def record(
        self,
        *,
        kind: SecurityEventKind,
        user_id: uuid.UUID | None,
        correlation_id: str | None,
        fields: dict[str, Any],
        occurred_at: datetime,
    ) -> SecurityEvent: ...

    async def delete_before(self, cutoff: datetime, *, batch_size: int) -> int: ...


class SqlSecurityEventRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def record(
        self,
        *,
        kind: SecurityEventKind,
        user_id: uuid.UUID | None,
        correlation_id: str | None,
        fields: dict[str, Any],
        occurred_at: datetime,
    ) -> SecurityEvent:
        """Add one row to the session, without flushing."""
        raise NotImplementedError

    async def delete_before(self, cutoff: datetime, *, batch_size: int) -> int:
        """Delete at most `batch_size` rows older than `cutoff`, returning how many went."""
        raise NotImplementedError
