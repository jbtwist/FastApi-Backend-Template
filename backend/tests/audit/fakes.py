"""In-memory stand-ins for the audit repositories."""

import uuid
from datetime import datetime
from typing import Any

from backend.audit.models import SecurityEvent, SecurityEventKind


class FakeSecurityEventRepository:
    def __init__(self) -> None:
        self.events: list[SecurityEvent] = []

    async def record(
        self,
        *,
        kind: SecurityEventKind,
        user_id: uuid.UUID | None,
        correlation_id: str | None,
        fields: dict[str, Any],
        occurred_at: datetime,
    ) -> SecurityEvent:
        event = SecurityEvent(
            id=uuid.uuid4(),
            kind=kind,
            user_id=user_id,
            correlation_id=correlation_id,
            fields=fields,
            occurred_at=occurred_at,
        )
        self.events.append(event)
        return event

    async def delete_before(self, cutoff: datetime, *, batch_size: int) -> int:
        expired = [event.id for event in self.events if event.occurred_at < cutoff][:batch_size]
        self.events = [event for event in self.events if event.id not in set(expired)]
        return len(expired)
