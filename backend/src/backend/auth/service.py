import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from backend.auth.config import AuthConfig
from backend.auth.exceptions import (
    EmailAlreadyRegistered,
    InvalidCredentials,
    InvalidRefreshToken,
    RefreshTokenExpired,
    RefreshTokenReuseDetected,
)
from backend.auth.models import RefreshToken, User
from backend.auth.security import (
    DUMMY_PASSWORD_HASH,
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)


class UserRepository(Protocol):
    async def get_by_email(self, email: str) -> User | None: ...
    async def get_by_id(self, user_id: uuid.UUID) -> User | None: ...
    async def create(self, *, email: str, password_hash: str) -> User: ...


class RefreshTokenRepository(Protocol):
    async def create(
        self,
        *,
        user_id: uuid.UUID,
        family_id: uuid.UUID,
        token_hash: str,
        expires_at: datetime,
    ) -> RefreshToken: ...
    async def get_by_hash(self, token_hash: str) -> RefreshToken | None: ...
    async def mark_used(self, token_id: uuid.UUID, *, used_at: datetime) -> bool: ...
    async def revoke_family(self, family_id: uuid.UUID, *, revoked_at: datetime) -> None: ...


@dataclass
class TokenPair:
    access_token: str
    refresh_token: str


def _normalize_email(email: str) -> str:
    return email.strip().lower()


async def register_user(user_repo: UserRepository, *, email: str, password: str) -> User:
    normalized_email = _normalize_email(email)
    existing = await user_repo.get_by_email(normalized_email)
    if existing is not None:
        raise EmailAlreadyRegistered

    password_hash = hash_password(password)
    return await user_repo.create(email=normalized_email, password_hash=password_hash)


async def authenticate_user(user_repo: UserRepository, *, email: str, password: str) -> User:
    normalized_email = _normalize_email(email)
    user = await user_repo.get_by_email(normalized_email)
    password_hash = user.password_hash if user is not None else DUMMY_PASSWORD_HASH
    password_valid = verify_password(password, password_hash)

    if user is None or not password_valid:
        raise InvalidCredentials

    return user


async def issue_token_pair(
    refresh_token_repo: RefreshTokenRepository,
    user: User,
    *,
    config: AuthConfig,
    now: datetime,
) -> TokenPair:
    access_token = create_access_token(str(user.id), config=config, now=now)
    raw_refresh_token = generate_refresh_token(config=config)

    await refresh_token_repo.create(
        user_id=user.id,
        family_id=uuid.uuid4(),
        token_hash=hash_refresh_token(raw_refresh_token),
        expires_at=now + config.REFRESH_TOKEN_EXP,
    )

    return TokenPair(access_token=access_token, refresh_token=raw_refresh_token)


async def rotate_refresh_token(
    refresh_token_repo: RefreshTokenRepository,
    raw_refresh_token: str,
    *,
    config: AuthConfig,
    now: datetime,
) -> TokenPair:
    record = await refresh_token_repo.get_by_hash(hash_refresh_token(raw_refresh_token))
    if record is None or record.revoked_at is not None:
        raise InvalidRefreshToken

    if record.used_at is not None:
        await refresh_token_repo.revoke_family(record.family_id, revoked_at=now)
        raise RefreshTokenReuseDetected

    if record.expires_at <= now:
        raise RefreshTokenExpired

    won_race = await refresh_token_repo.mark_used(record.id, used_at=now)
    if not won_race:
        await refresh_token_repo.revoke_family(record.family_id, revoked_at=now)
        raise RefreshTokenReuseDetected

    new_raw_refresh_token = generate_refresh_token(config=config)
    await refresh_token_repo.create(
        user_id=record.user_id,
        family_id=record.family_id,
        token_hash=hash_refresh_token(new_raw_refresh_token),
        expires_at=now + config.REFRESH_TOKEN_EXP,
    )

    access_token = create_access_token(str(record.user_id), config=config, now=now)
    return TokenPair(access_token=access_token, refresh_token=new_raw_refresh_token)


async def logout(
    refresh_token_repo: RefreshTokenRepository, raw_refresh_token: str, *, now: datetime
) -> None:
    record = await refresh_token_repo.get_by_hash(hash_refresh_token(raw_refresh_token))
    if record is None:
        return

    await refresh_token_repo.revoke_family(record.family_id, revoked_at=now)
