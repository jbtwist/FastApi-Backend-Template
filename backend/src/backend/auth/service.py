"""Registration, login, token rotation, and email verification business logic."""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from backend.auth.config import AuthConfig
from backend.auth.exceptions import (
    EmailAlreadyRegistered,
    EmailNotVerified,
    InvalidCredentials,
    InvalidPasswordResetToken,
    InvalidRefreshToken,
    InvalidVerificationToken,
    PasswordResetTokenExpired,
    RefreshTokenExpired,
    RefreshTokenReuseDetected,
    VerificationTokenExpired,
)
from backend.auth.models import (
    EmailVerificationToken,
    PasswordResetToken,
    RefreshToken,
    User,
)
from backend.auth.security import (
    DUMMY_PASSWORD_HASH,
    create_access_token,
    generate_opaque_token,
    hash_opaque_token,
    hash_password,
    verify_password,
)
from backend.mail import service as mail_service
from backend.mail.models import EmailKind, EmailOutboxEntry
from backend.mail.service import EmailOutboxRepository


class UserRepository(Protocol):
    async def get_by_email(self, email: str) -> User | None: ...
    async def get_by_id(self, user_id: uuid.UUID) -> User | None: ...
    async def create(self, *, email: str, password_hash: str) -> User: ...
    async def mark_email_verified(self, user_id: uuid.UUID, *, verified_at: datetime) -> bool: ...
    async def set_password_hash(
        self, user_id: uuid.UUID, *, password_hash: str, updated_at: datetime
    ) -> bool: ...


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
    async def revoke_all_for_user(self, user_id: uuid.UUID, *, revoked_at: datetime) -> None: ...


class EmailVerificationTokenRepository(Protocol):
    async def create(
        self, *, user_id: uuid.UUID, token_hash: str, expires_at: datetime
    ) -> EmailVerificationToken: ...
    async def get_by_hash(self, token_hash: str) -> EmailVerificationToken | None: ...
    async def mark_used(self, token_id: uuid.UUID, *, used_at: datetime) -> bool: ...


class PasswordResetTokenRepository(Protocol):
    async def create(
        self, *, user_id: uuid.UUID, token_hash: str, expires_at: datetime
    ) -> PasswordResetToken: ...
    async def get_by_hash(self, token_hash: str) -> PasswordResetToken | None: ...
    async def mark_used(self, token_id: uuid.UUID, *, used_at: datetime) -> bool: ...
    async def invalidate_all_for_user(
        self, user_id: uuid.UUID, *, invalidated_at: datetime
    ) -> None: ...


@dataclass
class TokenPair:
    """An access token and refresh token issued together, e.g. at login or refresh."""

    access_token: str
    refresh_token: str


def _normalize_email(email: str) -> str:
    return email.strip().lower()


async def ensure_email_available(user_repo: UserRepository, *, email: str) -> None:
    """Raise `EmailAlreadyRegistered` if the normalized email is taken.

    A cheap gate the register handler runs before the password policy, so a
    duplicate signup 409s without paying for an outbound breach-check call.

    Raises:
        EmailAlreadyRegistered: a user with the normalized email already exists.
    """
    if await user_repo.get_by_email(_normalize_email(email)) is not None:
        raise EmailAlreadyRegistered


async def register_user(user_repo: UserRepository, *, email: str, password: str) -> User:
    """Create a new user with a hashed password.

    Email is lowercased/trimmed before lookup and storage.

    Raises:
        EmailAlreadyRegistered: a user with the normalized email already exists.
    """
    normalized_email = _normalize_email(email)
    existing = await user_repo.get_by_email(normalized_email)
    if existing is not None:
        raise EmailAlreadyRegistered

    password_hash = hash_password(password)
    return await user_repo.create(email=normalized_email, password_hash=password_hash)


async def authenticate_user(user_repo: UserRepository, *, email: str, password: str) -> User:
    """Verify credentials and return the matching user.

    Always runs a password hash comparison, even for an unknown email (against
    `DUMMY_PASSWORD_HASH`), so an unregistered email and a wrong password take
    the same time and can't be told apart by a timing attack.

    Raises:
        InvalidCredentials: the email is unknown or the password doesn't match.
        EmailNotVerified: the credentials are correct but the account's email
            hasn't been confirmed yet.
    """
    normalized_email = _normalize_email(email)
    user = await user_repo.get_by_email(normalized_email)
    password_hash = user.password_hash if user is not None else DUMMY_PASSWORD_HASH
    password_valid = verify_password(password, password_hash)

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
) -> TokenPair:
    """Exchange a refresh token for a new pair, retiring the old one within its family.

    Each refresh token is single-use: this consumes `raw_refresh_token` and
    issues a replacement in the same `family_id`. If a token that was already
    used (or already lost the race to be marked used) is presented again,
    that's treated as a stolen/replayed token — the whole family is revoked,
    which signs out every device sharing that login's rotation chain.

    Raises:
        InvalidRefreshToken: the token doesn't exist or its family was already revoked.
        RefreshTokenExpired: the token exists but is past `expires_at`.
        RefreshTokenReuseDetected: the token was already used once before (reuse/replay).
    """
    record = await refresh_token_repo.get_by_hash(hash_opaque_token(raw_refresh_token))
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


async def queue_verification_email(
    token_repo: EmailVerificationTokenRepository,
    outbox_repo: EmailOutboxRepository,
    user: User,
    *,
    config: AuthConfig,
    now: datetime,
) -> EmailOutboxEntry:
    """Mint a verification token for `user` and durably queue the confirmation email.

    Writes the outbox row in the same call (and, at the call site, the same DB
    transaction as registration) so the email survives even if the Celery
    dispatch that follows never fires — see `backend.mail.service.enqueue_email`.
    """
    raw_token = generate_opaque_token()
    await token_repo.create(
        user_id=user.id,
        token_hash=hash_opaque_token(raw_token),
        expires_at=now + config.EMAIL_VERIFICATION_TOKEN_EXP,
    )
    return await mail_service.enqueue_email(
        outbox_repo, user_id=user.id, email=user.email, token=raw_token, created_at=now
    )


async def confirm_email(
    token_repo: EmailVerificationTokenRepository,
    user_repo: UserRepository,
    raw_token: str,
    *,
    now: datetime,
) -> User:
    """Consume a verification token and mark its user's email as verified.

    Raises:
        InvalidVerificationToken: the token doesn't exist, was already used,
            or lost the race to be marked used (double-submit).
        VerificationTokenExpired: the token exists but is past `expires_at`.
    """
    record = await token_repo.get_by_hash(hash_opaque_token(raw_token))
    if record is None or record.used_at is not None:
        raise InvalidVerificationToken

    if record.expires_at <= now:
        raise VerificationTokenExpired

    won_race = await token_repo.mark_used(record.id, used_at=now)
    if not won_race:
        raise InvalidVerificationToken

    await user_repo.mark_email_verified(record.user_id, verified_at=now)
    user = await user_repo.get_by_id(record.user_id)
    assert user is not None
    return user


async def resend_verification_email(
    token_repo: EmailVerificationTokenRepository,
    user_repo: UserRepository,
    outbox_repo: EmailOutboxRepository,
    *,
    email: str,
    config: AuthConfig,
    now: datetime,
) -> EmailOutboxEntry | None:
    """Re-queue the verification email for an unverified user, identified by email.

    Returns `None` without raising or revealing anything if the email is
    unregistered or already verified — callers should treat both cases the
    same as a normal "check your inbox" response, to avoid leaking whether an
    email is registered.
    """
    normalized_email = _normalize_email(email)
    user = await user_repo.get_by_email(normalized_email)
    if user is None or user.email_verified_at is not None:
        return None

    return await queue_verification_email(token_repo, outbox_repo, user, config=config, now=now)


async def request_password_reset(
    password_reset_token_repo: PasswordResetTokenRepository,
    user_repo: UserRepository,
    outbox_repo: EmailOutboxRepository,
    *,
    email: str,
    config: AuthConfig,
    now: datetime,
) -> EmailOutboxEntry | None:
    """Mint a password-reset token for a verified user and durably queue the reset email.

    Returns `None` without raising or revealing anything if the email is
    unregistered or not yet verified — callers must treat both the same as the
    success case (a bare "check your inbox" response) so the endpoint can't be
    used to enumerate registered addresses. An unverified address also hasn't
    been proven to belong to the account, so it can't be used to take it over.

    Repeated calls issue independent tokens; prior tokens are only invalidated
    once a reset actually completes (see `reset_password`).
    """
    normalized_email = _normalize_email(email)
    user = await user_repo.get_by_email(normalized_email)
    if user is None or user.email_verified_at is None:
        return None

    raw_token = generate_opaque_token()
    await password_reset_token_repo.create(
        user_id=user.id,
        token_hash=hash_opaque_token(raw_token),
        expires_at=now + config.PASSWORD_RESET_TOKEN_EXP,
    )
    return await mail_service.enqueue_email(
        outbox_repo,
        user_id=user.id,
        email=user.email,
        token=raw_token,
        created_at=now,
        kind=EmailKind.PASSWORD_RESET,
    )


async def assert_reset_token_valid(
    password_reset_token_repo: PasswordResetTokenRepository,
    raw_token: str,
    *,
    now: datetime,
) -> None:
    """Check that a reset token exists, is unused and unexpired — without consuming it.

    Lets the router reject a bad token (cheap: one hash + one indexed lookup)
    before running the password policy, which may make an outbound breach-check
    call. `reset_password` re-runs these checks and additionally guards the
    consume race, so this is an optimisation, not the security boundary.

    Raises:
        InvalidPasswordResetToken: the token doesn't exist or was already used.
        PasswordResetTokenExpired: the token exists but is at/past `expires_at`.
    """
    record = await password_reset_token_repo.get_by_hash(hash_opaque_token(raw_token))
    if record is None or record.used_at is not None:
        raise InvalidPasswordResetToken
    if record.expires_at <= now:
        raise PasswordResetTokenExpired


async def reset_password(
    password_reset_token_repo: PasswordResetTokenRepository,
    user_repo: UserRepository,
    refresh_token_repo: RefreshTokenRepository,
    raw_token: str,
    *,
    new_password: str,
    now: datetime,
) -> None:
    """Consume a reset token, set a new password, and sign the user out everywhere.

    On success: the password is re-hashed with argon2, every refresh-token
    session for that user is revoked, and every other outstanding reset token
    for that user is burned so a second issued-but-unused link can't be
    redeemed afterwards.

    Raises:
        InvalidPasswordResetToken: the token doesn't exist, was already used,
            or lost the race to be marked used (concurrent reset).
        PasswordResetTokenExpired: the token exists but is at/past `expires_at`;
            the password is left unchanged.
    """
    record = await password_reset_token_repo.get_by_hash(hash_opaque_token(raw_token))
    if record is None or record.used_at is not None:
        raise InvalidPasswordResetToken

    if record.expires_at <= now:
        raise PasswordResetTokenExpired

    won_race = await password_reset_token_repo.mark_used(record.id, used_at=now)
    if not won_race:
        raise InvalidPasswordResetToken

    await user_repo.set_password_hash(
        record.user_id, password_hash=hash_password(new_password), updated_at=now
    )
    await refresh_token_repo.revoke_all_for_user(record.user_id, revoked_at=now)
    await password_reset_token_repo.invalidate_all_for_user(record.user_id, invalidated_at=now)
