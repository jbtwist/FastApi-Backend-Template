import uuid
from datetime import datetime
from typing import Protocol

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.oauth.contract import ProviderIdentity
from backend.auth.oauth.models import OAuthIdentity, OAuthLinkToken
from backend.auth.repository import SingleUseTokenRepository, _SqlSingleUseTokenRepository


class OAuthIdentityRepository(Protocol):
    async def get_by_provider_subject(
        self, provider: str, provider_subject: str
    ) -> OAuthIdentity | None: ...

    async def get_by_user_id(self, user_id: uuid.UUID) -> OAuthIdentity | None:
        """The one provider identity linked to `user_id`, if any."""
        ...

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
            IntegrityError: `(provider, provider_subject)` is already linked, or
                `user_id` already has an identity. Enforced by the database, not
                a prior lookup, so concurrent first sign-ins can't both succeed.
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

    async def get_by_user_id(self, user_id: uuid.UUID) -> OAuthIdentity | None:
        result = await self._db.execute(
            select(OAuthIdentity).where(OAuthIdentity.user_id == user_id)
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
        async with self._db.begin_nested():
            self._db.add(identity)
        return identity

    async def mark_authenticated(
        self, identity_id: uuid.UUID, *, authenticated_at: datetime
    ) -> None:
        await self._db.execute(
            update(OAuthIdentity)
            .where(OAuthIdentity.id == identity_id)
            .values(last_authenticated_at=authenticated_at)
        )


class OAuthLinkTokenRepository(SingleUseTokenRepository, Protocol):
    async def create(
        self,
        *,
        user_id: uuid.UUID,
        token_hash: str,
        expires_at: datetime,
        identity: ProviderIdentity,
    ) -> OAuthLinkToken:
        """Store a pending link, freezing `identity`'s provider, subject and contact data."""
        ...

    async def get_by_hash(self, token_hash: str) -> OAuthLinkToken | None: ...

    async def invalidate_all_for_user(
        self, user_id: uuid.UUID, *, invalidated_at: datetime
    ) -> None:
        """Mark every unused link token of `user_id` used, so only the newest can be redeemed."""
        ...


class SqlOAuthLinkTokenRepository(_SqlSingleUseTokenRepository[OAuthLinkToken]):
    model = OAuthLinkToken

    async def create(
        self,
        *,
        user_id: uuid.UUID,
        token_hash: str,
        expires_at: datetime,
        identity: ProviderIdentity,
    ) -> OAuthLinkToken:
        token = OAuthLinkToken(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            provider=identity.provider,
            provider_subject=identity.subject,
            email_at_link=identity.email,
            is_private_relay=identity.is_private_relay,
            display_name=identity.display_name,
        )
        self._db.add(token)
        await self._db.flush()
        return token

    async def invalidate_all_for_user(
        self, user_id: uuid.UUID, *, invalidated_at: datetime
    ) -> None:
        await self._db.execute(
            update(OAuthLinkToken)
            .where(OAuthLinkToken.user_id == user_id, OAuthLinkToken.used_at.is_(None))
            .values(used_at=invalidated_at)
        )
