"""Credential check and the refresh-token rotation lifecycle of a login session."""

import uuid
from dataclasses import dataclass
from datetime import datetime

from backend.auth.config import AuthConfig
from backend.auth.exceptions import (
    EmailNotVerified,
    InvalidCredentials,
    InvalidRefreshToken,
    RefreshTokenExpired,
)
from backend.auth.models import User
from backend.auth.repository import RefreshTokenRepository, UserRepository
from backend.auth.security import (
    DUMMY_PASSWORD_HASH,
    create_access_token,
    generate_opaque_token,
    hash_opaque_token,
    verify_password,
)


@dataclass
class TokenPair:
    """An access token and refresh token issued together, e.g. at login or refresh."""

    access_token: str
    refresh_token: str


@dataclass
class ReuseDetected:
    """A spent refresh token was presented again; its family is now revoked.

    Returned rather than raised so that the revocation reaches the database.
    A request is one transaction and an exception leaving the endpoint rolls it back.
    The caller still answers 401.
    """

    family_id: uuid.UUID


async def authenticate_user(user_repo: UserRepository, *, email: str, password: str) -> User:
    """Verify credentials and return the matching user.

    Always runs a password hash comparison, against `DUMMY_PASSWORD_HASH` for an
    unknown email or an account with no password (one created through a sign-in
    provider), so neither can be told apart from a wrong password by a timing
    attack.

    Raises:
        InvalidCredentials: the email is unknown, the account has no password,
            or the password doesn't match.
        EmailNotVerified: the credentials are correct but the account's email
            hasn't been confirmed yet.
    """
    normalized_email = email.strip().lower()
    user = await user_repo.get_by_email(normalized_email)
    password_hash = user.password_hash if user is not None else None
    password_valid = verify_password(password, password_hash or DUMMY_PASSWORD_HASH)

    if user is None or not password_valid:
        raise InvalidCredentials

    if user.email_verified_at is None:
        raise EmailNotVerified

    return user


async def issue_token_pair(
    refresh_token_repo: RefreshTokenRepository,
    user: User,
    *,
    config: AuthConfig,
    now: datetime,
) -> TokenPair:
    """Issue a fresh access/refresh token pair for a new session, starting a new rotation family.

    Each call (e.g. one per login) gets its own `family_id`, so revoking one
    session's family (see `rotate_refresh_token`) never affects the user's
    other sessions/devices.
    """
    access_token = create_access_token(str(user.id), config=config, now=now)
    raw_refresh_token = generate_opaque_token()

    await refresh_token_repo.create(
        user_id=user.id,
        family_id=uuid.uuid4(),
        token_hash=hash_opaque_token(raw_refresh_token),
        expires_at=now + config.REFRESH_TOKEN_EXP,
    )

    return TokenPair(access_token=access_token, refresh_token=raw_refresh_token)


async def rotate_refresh_token(
    refresh_token_repo: RefreshTokenRepository,
    raw_refresh_token: str,
    *,
    config: AuthConfig,
    now: datetime,
) -> TokenPair | ReuseDetected:
    """Exchange a refresh token for a new pair, retiring the old one within its family.

    Each refresh token is single-use: this consumes `raw_refresh_token` and
    issues a replacement in the same `family_id`. If a token that was already
    used is presented again, that's treated as a stolen token and the whole family is revoked,
    which signs out every device sharing that login's rotation chain.

    Returns:
        The new `TokenPair`, or `ReuseDetected` if `raw_refresh_token` had
        already been spent. Reuse is a return value, not an exception, because
        the revocation it performs has to survive the 401 the caller sends
        back; see `ReuseDetected`.

    Raises:
        InvalidRefreshToken: the token doesn't exist or its family was already revoked.
        RefreshTokenExpired: the token exists but is past `expires_at`.
    """
    record = await refresh_token_repo.get_by_hash(hash_opaque_token(raw_refresh_token))
    if record is None or record.revoked_at is not None:
        raise InvalidRefreshToken

    if record.used_at is not None:
        await refresh_token_repo.revoke_family(record.family_id, revoked_at=now)
        return ReuseDetected(family_id=record.family_id)

    if record.expires_at <= now:
        raise RefreshTokenExpired

    won_race = await refresh_token_repo.mark_used(record.id, used_at=now)
    if not won_race:
        await refresh_token_repo.revoke_family(record.family_id, revoked_at=now)
        return ReuseDetected(family_id=record.family_id)

    new_raw_refresh_token = generate_opaque_token()
    await refresh_token_repo.create(
        user_id=record.user_id,
        family_id=record.family_id,
        token_hash=hash_opaque_token(new_raw_refresh_token),
        expires_at=now + config.REFRESH_TOKEN_EXP,
    )

    access_token = create_access_token(str(record.user_id), config=config, now=now)
    return TokenPair(access_token=access_token, refresh_token=new_raw_refresh_token)


async def logout(
    refresh_token_repo: RefreshTokenRepository, raw_refresh_token: str, *, now: datetime
) -> None:
    """Revoke the refresh token's entire family, signing out every device on that session.

    Silently no-ops if the token doesn't exist — logout is idempotent.
    """
    record = await refresh_token_repo.get_by_hash(hash_opaque_token(raw_refresh_token))
    if record is None:
        return

    await refresh_token_repo.revoke_family(record.family_id, revoked_at=now)
