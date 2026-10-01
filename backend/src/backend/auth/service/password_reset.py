"""Password-reset request, token validation, and the reset itself."""

import logging
from datetime import datetime

from backend.auth.config import AuthConfig
from backend.auth.exceptions import InvalidPasswordResetToken, PasswordResetTokenExpired
from backend.auth.repository import (
    PasswordResetTokenRepository,
    RefreshTokenRepository,
    UserRepository,
)
from backend.auth.security import generate_opaque_token, hash_opaque_token, hash_password
from backend.log import audit_logger, log_event
from backend.mail import service as mail_service
from backend.mail.models import EmailKind, EmailOutboxEntry
from backend.mail.service import EmailOutboxRepository

audit = audit_logger("auth")


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

    Returns `None` if the email is unregistered or unverified, so the endpoint
    can't enumerate addresses. An unverified address hasn't been proven to belong
    to the account either, so it can't be used to take one over.

    Repeated calls issue independent tokens; earlier ones are invalidated only
    once a reset completes.
    """
    normalized_email = email.strip().lower()
    user = await user_repo.get_by_email(normalized_email)
    if user is None or user.email_verified_at is None:
        log_event(
            audit,
            "password.reset_skipped",
            reason="unknown_email" if user is None else "email_unverified",
        )
        return None

    raw_token = generate_opaque_token()
    await password_reset_token_repo.create(
        user_id=user.id,
        token_hash=hash_opaque_token(raw_token),
        expires_at=now + config.PASSWORD_RESET_TOKEN_EXP,
    )
    log_event(audit, "password.reset_requested", user_id=user.id)
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
    """Check that a reset token exists, is unused and unexpired without consuming it.

    Lets the router reject a bad token before the password policy makes its
    outbound breach-check call. `reset_password` re-runs these checks and guards
    the consume race, so this is an optimisation, not the security boundary.

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

    Every other outstanding reset token for the user is burned too, so a second
    issued-but-unused link can't be redeemed afterwards.

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
        log_event(
            audit,
            "password.reset_race_lost",
            level=logging.WARNING,
            user_id=record.user_id,
            token_id=record.id,
        )
        raise InvalidPasswordResetToken

    await user_repo.set_password_hash(
        record.user_id, password_hash=hash_password(new_password), updated_at=now
    )
    await refresh_token_repo.revoke_all_for_user(record.user_id, revoked_at=now)
    await password_reset_token_repo.invalidate_all_for_user(record.user_id, invalidated_at=now)
    log_event(audit, "password.reset_completed", user_id=record.user_id)
    log_event(audit, "sessions.revoked_all", user_id=record.user_id, reason="password_reset")
