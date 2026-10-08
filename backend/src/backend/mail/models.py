import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from backend.database import Base


class EmailOutboxStatus(StrEnum):
    PENDING = "pending"
    SENDING = "sending"
    SENT = "sent"
    DEAD = "dead"


class EmailKind(StrEnum):
    """Which transactional email an outbox row carries.

    Dispatch picks the template and sender method by this value, and `token`
    holds whichever opaque token that kind's link needs.
    """

    VERIFICATION = "verification"
    PASSWORD_RESET = "password_reset"
    OAUTH_LINK = "oauth_link"


class EmailOutboxEntry(Base):
    __tablename__ = "email_outbox"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("user.id"), nullable=False
    )
    email: Mapped[str] = mapped_column(String, nullable=False)
    token: Mapped[str] = mapped_column(String, nullable=False)
    kind: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default=EmailKind.VERIFICATION,
        server_default=EmailKind.VERIFICATION.value,
    )
    status: Mapped[str] = mapped_column(String, nullable=False, default=EmailOutboxStatus.PENDING)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_attempted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    dead_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
