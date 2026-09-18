import uuid
from datetime import datetime
from typing import Any, Protocol

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.models import (
    EmailVerificationToken,
    PasswordResetToken,
    RefreshToken,
    User,
)


class UserRepository(Protocol):
    async def get_by_email(self, email: str) -> User | None: ...
    async def get_by_id(self, user_id: uuid.UUID) -> User | None: ...
    async def create(self, *, email: str, password_hash: str | None) -> User:
        """Store a new user.

        Raises:
            IntegrityError: the email is already registered. The insert runs in
                a savepoint, so the caller's transaction survives the conflict.
        """
        ...

    async def mark_email_verified(self, user_id: uuid.UUID, *, verified_at: datetime) -> bool: ...
    async def set_password_hash(
        self, user_id: uuid.UUID, *, password_hash: str | None, updated_at: datetime
    ) -> bool: ...


class SqlUserRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_by_email(self, email: str) -> User | None:
        result = await self._db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return await self._db.get(User, user_id)

    async def create(self, *, email: str, password_hash: str | None) -> User:
        user = User(email=email, password_hash=password_hash)
        async with self._db.begin_nested():
            self._db.add(user)
        return user

    async def mark_email_verified(self, user_id: uuid.UUID, *, verified_at: datetime) -> bool:
        result = await self._db.execute(
            update(User)
            .where(User.id == user_id, User.email_verified_at.is_(None))
            .values(email_verified_at=verified_at)
        )
        return result.rowcount == 1

    async def set_password_hash(
        self, user_id: uuid.UUID, *, password_hash: str | None, updated_at: datetime
    ) -> bool:
        result = await self._db.execute(
            update(User)
            .where(User.id == user_id)
            .values(password_hash=password_hash, updated_at=updated_at)
        )
        return result.rowcount == 1


class SingleUseTokenRepository(Protocol):
    """Contract shared by every hashed, expiring, one-shot token repository."""

    async def create(self, *, user_id: uuid.UUID, token_hash: str, expires_at: datetime) -> Any: ...
    async def get_by_hash(self, token_hash: str) -> Any | None: ...
    async def mark_used(self, token_id: uuid.UUID, *, used_at: datetime) -> bool: ...


class EmailVerificationTokenRepository(SingleUseTokenRepository, Protocol):
    async def get_by_hash(self, token_hash: str) -> EmailVerificationToken | None: ...


class PasswordResetTokenRepository(SingleUseTokenRepository, Protocol):
    async def get_by_hash(self, token_hash: str) -> PasswordResetToken | None: ...
    async def invalidate_all_for_user(
        self, user_id: uuid.UUID, *, invalidated_at: datetime
    ) -> None: ...


class RefreshTokenRepository(SingleUseTokenRepository, Protocol):
    async def create(
        self,
        *,
        user_id: uuid.UUID,
        family_id: uuid.UUID,
        token_hash: str,
        expires_at: datetime,
    ) -> RefreshToken: ...
    async def get_by_hash(self, token_hash: str) -> RefreshToken | None: ...
    async def revoke_family(self, family_id: uuid.UUID, *, revoked_at: datetime) -> None: ...
    async def revoke_all_for_user(self, user_id: uuid.UUID, *, revoked_at: datetime) -> None: ...


class _SqlSingleUseTokenRepository[TokenT]:
    """SQL storage for a single-use token table; `model` is set by each subclass."""

    model: type[TokenT]

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(self, *, user_id: uuid.UUID, token_hash: str, expires_at: datetime) -> TokenT:
        token = self.model(user_id=user_id, token_hash=token_hash, expires_at=expires_at)
        self._db.add(token)
        await self._db.flush()
        return token

    async def get_by_hash(self, token_hash: str) -> TokenT | None:
        result = await self._db.execute(
            select(self.model).where(self.model.token_hash == token_hash)
        )
        return result.scalar_one_or_none()

    async def mark_used(self, token_id: uuid.UUID, *, used_at: datetime) -> bool:
        result = await self._db.execute(
            update(self.model)
            .where(self.model.id == token_id, self.model.used_at.is_(None))
            .values(used_at=used_at)
        )
        return result.rowcount == 1


class SqlEmailVerificationTokenRepository(_SqlSingleUseTokenRepository[EmailVerificationToken]):
    model = EmailVerificationToken


class SqlPasswordResetTokenRepository(_SqlSingleUseTokenRepository[PasswordResetToken]):
    model = PasswordResetToken

    async def invalidate_all_for_user(
        self, user_id: uuid.UUID, *, invalidated_at: datetime
    ) -> None:
        await self._db.execute(
            update(PasswordResetToken)
            .where(PasswordResetToken.user_id == user_id, PasswordResetToken.used_at.is_(None))
            .values(used_at=invalidated_at)
        )


class SqlRefreshTokenRepository(_SqlSingleUseTokenRepository[RefreshToken]):
    model = RefreshToken

    async def create(
        self,
        *,
        user_id: uuid.UUID,
        family_id: uuid.UUID,
        token_hash: str,
        expires_at: datetime,
    ) -> RefreshToken:
        token = RefreshToken(
            user_id=user_id,
            family_id=family_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        self._db.add(token)
        await self._db.flush()
        return token

    async def revoke_family(self, family_id: uuid.UUID, *, revoked_at: datetime) -> None:
        result = await self._db.execute(
            select(RefreshToken).where(
                RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None)
            )
        )
        for token in result.scalars():
            token.revoked_at = revoked_at

    async def revoke_all_for_user(self, user_id: uuid.UUID, *, revoked_at: datetime) -> None:
        await self._db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=revoked_at)
        )
