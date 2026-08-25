import uuid
from datetime import datetime

from backend.auth.models import EmailVerificationToken, RefreshToken, User


class FakeUserRepository:
    def __init__(self) -> None:
        self._users_by_email: dict[str, User] = {}

    async def get_by_email(self, email: str) -> User | None:
        return self._users_by_email.get(email)

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        for user in self._users_by_email.values():
            if user.id == user_id:
                return user
        return None

    async def create(self, *, email: str, password_hash: str) -> User:
        user = User(id=uuid.uuid4(), email=email, password_hash=password_hash)
        self._users_by_email[email] = user
        return user

    async def mark_email_verified(self, user_id: uuid.UUID, *, verified_at: datetime) -> bool:
        user = await self.get_by_id(user_id)
        if user is None or user.email_verified_at is not None:
            return False
        user.email_verified_at = verified_at
        return True


class FakeRefreshTokenRepository:
    def __init__(self) -> None:
        self._tokens_by_id: dict[uuid.UUID, RefreshToken] = {}

    async def create(
        self,
        *,
        user_id: uuid.UUID,
        family_id: uuid.UUID,
        token_hash: str,
        expires_at: datetime,
    ) -> RefreshToken:
        token = RefreshToken(
            id=uuid.uuid4(),
            user_id=user_id,
            family_id=family_id,
            token_hash=token_hash,
            expires_at=expires_at,
            used_at=None,
            revoked_at=None,
        )
        self._tokens_by_id[token.id] = token
        return token

    async def get_by_hash(self, token_hash: str) -> RefreshToken | None:
        for token in self._tokens_by_id.values():
            if token.token_hash == token_hash:
                return token
        return None

    async def mark_used(self, token_id: uuid.UUID, *, used_at: datetime) -> bool:
        token = self._tokens_by_id[token_id]
        if token.used_at is not None:
            return False
        token.used_at = used_at
        return True

    async def revoke_family(self, family_id: uuid.UUID, *, revoked_at: datetime) -> None:
        for token in self._tokens_by_id.values():
            if token.family_id == family_id and token.revoked_at is None:
                token.revoked_at = revoked_at


class FakeEmailVerificationTokenRepository:
    def __init__(self) -> None:
        self._tokens_by_id: dict[uuid.UUID, EmailVerificationToken] = {}

    async def create(
        self, *, user_id: uuid.UUID, token_hash: str, expires_at: datetime
    ) -> EmailVerificationToken:
        token = EmailVerificationToken(
            id=uuid.uuid4(),
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            used_at=None,
        )
        self._tokens_by_id[token.id] = token
        return token

    async def get_by_hash(self, token_hash: str) -> EmailVerificationToken | None:
        for token in self._tokens_by_id.values():
            if token.token_hash == token_hash:
                return token
        return None

    async def mark_used(self, token_id: uuid.UUID, *, used_at: datetime) -> bool:
        token = self._tokens_by_id[token_id]
        if token.used_at is not None:
            return False
        token.used_at = used_at
        return True
