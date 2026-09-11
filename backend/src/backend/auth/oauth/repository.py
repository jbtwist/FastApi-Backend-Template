import uuid
from datetime import datetime
from typing import Protocol

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.oauth.models import OAuthIdentity


class OAuthIdentityRepository(Protocol):
    async def get_by_provider_subject(
        self, provider: str, provider_subject: str
    ) -> OAuthIdentity | None: ...

    async def create(
        self,
        *,
        user_id: uuid.UUID,
        provider: str,
        provider_subject: str,
        email_at_link: str | None,
        is_private_relay: bool,
        display_name: str | None,
    ) -> OAuthIdentity:
        """Store a new link.

        Raises:
            IntegrityError: `(provider, provider_subject)` is already linked. The
                database enforces this rather than a prior lookup, so two
                concurrent first sign-ins for one identity can't both succeed.
        """
        ...

    async def mark_authenticated(
        self, identity_id: uuid.UUID, *, authenticated_at: datetime
    ) -> None: ...


class SqlOAuthIdentityRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_by_provider_subject(
        self, provider: str, provider_subject: str
    ) -> OAuthIdentity | None:
        result = await self._db.execute(
            select(OAuthIdentity).where(
                OAuthIdentity.provider == provider,
                OAuthIdentity.provider_subject == provider_subject,
            )
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        user_id: uuid.UUID,
        provider: str,
        provider_subject: str,
        email_at_link: str | None,
        is_private_relay: bool,
        display_name: str | None,
    ) -> OAuthIdentity:
        identity = OAuthIdentity(
            user_id=user_id,
            provider=provider,
            provider_subject=provider_subject,
            email_at_link=email_at_link,
            is_private_relay=is_private_relay,
            display_name=display_name,
        )
        self._db.add(identity)
        await self._db.flush()
        return identity

    async def mark_authenticated(
        self, identity_id: uuid.UUID, *, authenticated_at: datetime
    ) -> None:
        await self._db.execute(
            update(OAuthIdentity)
            .where(OAuthIdentity.id == identity_id)
            .values(last_authenticated_at=authenticated_at)
        )
