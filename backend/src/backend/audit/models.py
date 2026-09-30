"""The durable security-event table.

A `security_event` row is the subset of `audit_event` that must outlive the log
stream: a shipper drops records under backpressure and retains them for weeks,
which is the wrong guarantee for the records that answer who signed in, who
reset a password, and whose refresh token was replayed.

`fields` holds the same structured data the matching log line carries, already
scrubbed. Values go in JSON-safe, so a caller passing a `UUID` gets a string.

The table is append-only and time-retained, which drives two choices. Ids are
`uuid7`, not `uuid4`: a time-ordered key appends at the right edge of the index
instead of scattering across leaf pages, which avoids the page splits and
full-page WAL writes a random key causes on an insert-heavy table. The embedded
timestamp leaks nothing, `occurred_at` is already a column here. And `kind` is
deliberately unindexed, at eight distinct values it would never be chosen.
"""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from backend.database import Base


class SecurityEventKind(StrEnum):
    """The closed set of actions that earn a durable row.

    Values match the `audit_event` names the same actions log, so a row and its
    log line join on more than a timestamp. Adding a member is a deliberate
    decision to retain that action for `SECURITY_EVENT_RETENTION_DAYS`.
    """

    USER_REGISTERED = "user.registered"
    EMAIL_VERIFIED = "email.verified"
    LOGIN_SUCCEEDED = "login.succeeded"
    LOGIN_FAILED = "login.failed"
    PASSWORD_RESET_REQUESTED = "password.reset_requested"
    PASSWORD_RESET_COMPLETED = "password.reset_completed"
    TOKEN_REUSE_DETECTED = "token.reuse_detected"
    TOKEN_FAMILY_REVOKED = "token.family_revoked"


class SecurityEvent(Base):
    __tablename__ = "security_event"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid7
    )
    kind: Mapped[str] = mapped_column(String, nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    correlation_id: Mapped[str | None] = mapped_column(String, nullable=True)
    fields: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )


Index(
    "security_event_user_id_idx",
    SecurityEvent.user_id,
    SecurityEvent.occurred_at.desc(),
)
