import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint, false
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from backend.database import Base


class OAuthIdentity(Base):
    """A link between a `user` and one account at a third-party sign-in provider.

    A credential of the user, beside `password_hash`, never a second kind of user.
    A returning person is found by `(provider, provider_subject)` alone, never by
    email; the unique constraint on that pair is what guarantees one provider
    identity maps to at most one account, even under concurrent first sign-ins.
    No provider token of any kind is stored. `email_at_link` is contact data only,
    and `display_name` is unsigned, untrusted and never rendered.
    """

    __tablename__ = "oauth_identity"
    __table_args__ = (
        UniqueConstraint(
            "provider", "provider_subject", name="oauth_identity_provider_subject_key"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("user.id"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String, nullable=False)
    provider_subject: Mapped[str] = mapped_column(String, nullable=False)
    email_at_link: Mapped[str | None] = mapped_column(String, nullable=True)
    is_private_relay: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=false())
    display_name: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_authenticated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
