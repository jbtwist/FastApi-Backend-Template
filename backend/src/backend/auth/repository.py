import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.models import (
    EmailVerificationToken,
    PasswordResetToken,
    RefreshToken,
    User,
)


class SqlUserRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_by_email(self, email: str) -> User | None:
        result = await self._db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return await self._db.get(User, user_id)

    async def create(self, *, email: str, password_hash: str) -> User:
        user = User(email=email, password_hash=password_hash)
        self._db.add(user)
        await self._db.flush()
        return user

    async def mark_email_verified(self, user_id: uuid.UUID, *, verified_at: datetime) -> bool:
        result = await self._db.execute(
            update(User)
            .where(User.id == user_id, User.email_verified_at.is_(None))
            .values(email_verified_at=verified_at)
        )
        return result.rowcount == 1

    async def set_password_hash(
        self, user_id: uuid.UUID, *, password_hash: str, updated_at: datetime
    ) -> bool:
        result = await self._db.execute(
            update(User)
            .where(User.id == user_id)
            .values(password_hash=password_hash, updated_at=updated_at)
        )
        return result.rowcount == 1


class SqlRefreshTokenRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

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

    async def get_by_hash(self, token_hash: str) -> RefreshToken | None:
        result = await self._db.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        return result.scalar_one_or_none()

    async def mark_used(self, token_id: uuid.UUID, *, used_at: datetime) -> bool:
        result = await self._db.execute(
            update(RefreshToken)
            .where(RefreshToken.id == token_id, RefreshToken.used_at.is_(None))
            .values(used_at=used_at)
        )
        return result.rowcount == 1

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


class SqlEmailVerificationTokenRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(
        self, *, user_id: uuid.UUID, token_hash: str, expires_at: datetime
    ) -> EmailVerificationToken:
        token = EmailVerificationToken(
            user_id=user_id, token_hash=token_hash, expires_at=expires_at
        )
        self._db.add(token)
        await self._db.flush()
        return token

    async def get_by_hash(self, token_hash: str) -> EmailVerificationToken | None:
        result = await self._db.execute(
            select(EmailVerificationToken).where(EmailVerificationToken.token_hash == token_hash)
        )
        return result.scalar_one_or_none()

    async def mark_used(self, token_id: uuid.UUID, *, used_at: datetime) -> bool:
        result = await self._db.execute(
            update(EmailVerificationToken)
            .where(EmailVerificationToken.id == token_id, EmailVerificationToken.used_at.is_(None))
            .values(used_at=used_at)
        )
        return result.rowcount == 1


class SqlPasswordResetTokenRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(
        self, *, user_id: uuid.UUID, token_hash: str, expires_at: datetime
    ) -> PasswordResetToken:
        token = PasswordResetToken(user_id=user_id, token_hash=token_hash, expires_at=expires_at)
        self._db.add(token)
        await self._db.flush()
        return token

    async def get_by_hash(self, token_hash: str) -> PasswordResetToken | None:
        result = await self._db.execute(
            select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)
        )
        return result.scalar_one_or_none()

    async def mark_used(self, token_id: uuid.UUID, *, used_at: datetime) -> bool:
        result = await self._db.execute(
            update(PasswordResetToken)
            .where(PasswordResetToken.id == token_id, PasswordResetToken.used_at.is_(None))
            .values(used_at=used_at)
        )
        return result.rowcount == 1

    async def invalidate_all_for_user(
        self, user_id: uuid.UUID, *, invalidated_at: datetime
    ) -> None:
        await self._db.execute(
            update(PasswordResetToken)
            .where(PasswordResetToken.user_id == user_id, PasswordResetToken.used_at.is_(None))
            .values(used_at=invalidated_at)
        )
