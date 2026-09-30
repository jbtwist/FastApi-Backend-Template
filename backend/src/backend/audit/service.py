"""Recording and expiring security events.

`record_security_event` is the only way a `security_event` row is written. It
feeds both sinks from one call, so a caller cannot write the row and forget the
log line, and it scrubs `SENSITIVE_FIELDS` before either: a durable table is a
worse place to leak a credential than a log stream that expires.
"""

import uuid
from datetime import datetime, timedelta
from typing import Any

from backend.audit.models import SecurityEvent, SecurityEventKind
from backend.audit.repository import SecurityEventRepository

_WARNING_KINDS = frozenset({SecurityEventKind.TOKEN_REUSE_DETECTED})


async def record_security_event(
    security_event_repo: SecurityEventRepository,
    kind: SecurityEventKind,
    *,
    user_id: uuid.UUID | None = None,
    occurred_at: datetime,
    **fields: Any,
) -> SecurityEvent:
    """Write one security event to Postgres and to stdout.

    Args:
        security_event_repo: Repository on the caller's session, so the row
            commits with the change it records.
        kind: Which action this is. Only members of `SecurityEventKind` earn a row.
        user_id: The account it belongs to, or `None` when there is none to
            attribute it to, as with a failed login for an unknown address.
        occurred_at: When the action happened.
        **fields: Structured detail. Values are coerced to JSON-safe types, and
            any name in `SENSITIVE_FIELDS` is replaced before the row is built.
    """
    raise NotImplementedError


async def purge_expired_security_events(
    security_event_repo: SecurityEventRepository,
    *,
    now: datetime,
    retention: timedelta,
    batch_size: int,
) -> int:
    """Delete up to `batch_size` events older than `retention`, returning how many went.

    One batch per call. A caller draining a backlog loops until this returns 0,
    committing between calls, so no single transaction spans the whole purge.

    A row exactly `retention` old is kept: the cutoff is exclusive, so a run at
    a slightly different time of day cannot make the window jitter.
    """
    raise NotImplementedError
