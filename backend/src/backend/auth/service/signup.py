"""Account creation and the email-verification flow that gates first login."""

from datetime import datetime

from backend.auth.config import AuthConfig
from backend.auth.exceptions import (
    EmailAlreadyRegistered,
    InvalidVerificationToken,
    VerificationTokenExpired,
)
from backend.auth.models import User
from backend.auth.repository import EmailVerificationTokenRepository, UserRepository
from backend.auth.security import (
    generate_opaque_token,
    hash_opaque_token,
    hash_password,
)
from backend.mail import service as mail_service
from backend.mail.models import EmailOutboxEntry
from backend.mail.service import EmailOutboxRepository


async def ensure_email_available(user_repo: UserRepository, *, email: str) -> None:
    """Raise `EmailAlreadyRegistered` if the normalized email is taken.

    A cheap gate the register handler runs before the password policy, so a
    duplicate signup 409s without paying for an outbound breach-check call.

    Raises:
        EmailAlreadyRegistered: a user with the normalized email already exists.
    """
    if await user_repo.get_by_email(email.strip().lower()) is not None:
        raise EmailAlreadyRegistered


async def register_user(user_repo: UserRepository, *, email: str, password: str) -> User:
    """Create a new user with a hashed password.

    Email is lowercased/trimmed before lookup and storage.

    Raises:
        EmailAlreadyRegistered: a user with the normalized email already exists.
    """
    normalized_email = email.strip().lower()
    existing = await user_repo.get_by_email(normalized_email)
    if existing is not None:
        raise EmailAlreadyRegistered

    password_hash = hash_password(password)
    return await user_repo.create(email=normalized_email, password_hash=password_hash)


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
    normalized_email = email.strip().lower()
    user = await user_repo.get_by_email(normalized_email)
    if user is None or user.email_verified_at is not None:
        return None

    return await queue_verification_email(token_repo, outbox_repo, user, config=config, now=now)
