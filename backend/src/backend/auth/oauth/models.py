import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint, false
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from backend.auth.models import SingleUseTokenMixin
from backend.database import Base


class OAuthIdentity(Base):
    """A link between a `user` and one account at a third-party sign-in provider.

    A credential of the user, beside `password_hash`, never a second kind of user.
    The unique constraint on `(provider, provider_subject)` is what holds one
    identity to at most one account under concurrent first sign-ins; `user_id` is
    unique too, so an account holds at most one identity.

    No provider token is stored. `email_at_link` is contact data only, and
    `display_name` is unsigned, untrusted and never rendered.
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
        PGUUID(as_uuid=True), ForeignKey("user.id"), nullable=False, unique=True
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


class OAuthLinkToken(SingleUseTokenMixin, Base):
    """A pending link of one verified provider identity to an existing `user`.

    Emailed to the account's address, so redeeming it proves the person signing
    in with the provider owns the account. The identity is frozen at mint time,
    so what gets linked is exactly what the provider verified.
    """

    __tablename__ = "oauth_link_token"

    provider: Mapped[str] = mapped_column(String, nullable=False)
    provider_subject: Mapped[str] = mapped_column(String, nullable=False)
    email_at_link: Mapped[str | None] = mapped_column(String, nullable=True)
    is_private_relay: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=false())
    display_name: Mapped[str | None] = mapped_column(String, nullable=True)
