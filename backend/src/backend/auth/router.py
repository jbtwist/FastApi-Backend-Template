"""`/auth` endpoints: registration, login, refresh, logout, email verification, password reset."""

import asyncio
import contextlib
import logging
import time
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse
from redis_fastapi import rate_limit

from backend.auth import service
from backend.auth.config import AuthConfig
from backend.auth.cookies import (
    access_token_cookie,
    clear_access_token_cookie,
    clear_refresh_token_cookie,
    refresh_token_cookie,
)
from backend.auth.dependencies import (
    AuthConfigDep,
    CurrentUserDep,
    EmailVerificationTokenRepoDep,
    PasswordResetTokenRepoDep,
    PwnedPasswordCheckerDep,
    RefreshTokenRepoDep,
    UserRepoDep,
)
from backend.auth.exceptions import (
    InvalidRefreshToken,
    InvalidVerificationToken,
    PasswordCompromised,
    PasswordTooLong,
    PasswordTooShort,
    RefreshTokenExpired,
    RefreshTokenReuseDetected,
    VerificationTokenExpired,
)
from backend.auth.password_policy import (
    MIN_LENGTH_BY_STRENGTH,
    PwnedPasswordChecker,
    validate_password_strength,
)
from backend.auth.schemas import (
    ConfirmEmailIn,
    ForgotPasswordIn,
    LoginIn,
    LoginOut,
    LogoutIn,
    RefreshIn,
    RegisterIn,
    ResendVerificationIn,
    ResetPasswordIn,
    TokenPairOut,
    UserOut,
)
from backend.mail.dependencies import EmailOutboxRepoDep
from backend.mail.tasks import dispatch_email

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


async def _queue_dispatch(entry_id: str) -> None:
    """Fire the Celery dispatch for a freshly queued outbox row, tolerating a broker outage.

    A failed enqueue must not surface to the caller: on `forgot-password` a 500
    for registered addresses (vs. 204 for unknown ones) would be an enumeration
    oracle. The row stays `PENDING`; `sweep_pending_emails` redelivers it.
    """
    try:
        await run_in_threadpool(dispatch_email.delay, entry_id)
    except Exception:
        logger.warning("dispatch enqueue failed for outbox entry %s", entry_id, exc_info=True)


async def _enforce_password_policy(
    password: str, *, config: AuthConfig, pwned_checker: PwnedPasswordChecker
) -> None:
    """Run the active password policy, translating each failure to a 422."""
    try:
        await validate_password_strength(password, config=config, pwned_checker=pwned_checker)
    except PasswordTooShort as exc:
        minimum = MIN_LENGTH_BY_STRENGTH[config.PASSWORD_STRENGTH]
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Password is too short (minimum {minimum} characters)",
        ) from exc
    except PasswordTooLong as exc:
        limit = config.PASSWORD_MAX_LENGTH
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Password exceeds the maximum length of {limit} characters",
        ) from exc
    except PasswordCompromised as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="This password has appeared in a data breach; choose another",
        ) from exc


@contextlib.asynccontextmanager
async def _response_floor(minimum: timedelta) -> AsyncGenerator:
    """Pad the enclosed work to at least `minimum` wall-clock time.

    Best-effort defence against a timing oracle — not a hard guarantee against
    scheduler jitter. A no-op when `minimum` is zero.
    """
    start = time.perf_counter()
    try:
        yield
    finally:
        remaining = minimum.total_seconds() - (time.perf_counter() - start)
        if remaining > 0:
            await asyncio.sleep(remaining)


def _set_token_cookies(
    response: Response, pair: service.TokenPair, *, config: AuthConfigDep
) -> None:
    response.set_cookie(**access_token_cookie(pair.access_token, config=config))
    response.set_cookie(**refresh_token_cookie(pair.refresh_token, config=config))


@router.post(
    "/register",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("5/minute"))],
)
async def register(
    payload: RegisterIn,
    user_repo: UserRepoDep,
    token_repo: EmailVerificationTokenRepoDep,
    outbox_repo: EmailOutboxRepoDep,
    config: AuthConfigDep,
    pwned_checker: PwnedPasswordCheckerDep,
) -> UserOut:
    """Create an account and queue a verification email. The account can't log in until verified."""
    await service.ensure_email_available(user_repo, email=payload.email)
    await _enforce_password_policy(payload.password, config=config, pwned_checker=pwned_checker)
    user = await service.register_user(user_repo, email=payload.email, password=payload.password)

    entry = await service.queue_verification_email(
        token_repo, outbox_repo, user, config=config, now=datetime.now(UTC)
    )
    await _queue_dispatch(str(entry.id))
    return UserOut(id=user.id, email=user.email, email_verified=False)


@router.post(
    "/login",
    response_model=LoginOut,
    dependencies=[Depends(rate_limit("10/minute"))],
)
async def login(
    payload: LoginIn,
    response: Response,
    user_repo: UserRepoDep,
    refresh_token_repo: RefreshTokenRepoDep,
    config: AuthConfigDep,
) -> LoginOut:
    """Authenticate and start a new session: sets token cookies and returns the tokens.

    The cookies are for the web client; the body is for non-browser clients.
    """
    user = await service.authenticate_user(
        user_repo, email=payload.email, password=payload.password
    )

    pair = await service.issue_token_pair(
        refresh_token_repo, user, config=config, now=datetime.now(UTC)
    )
    _set_token_cookies(response, pair, config=config)
    return LoginOut(
        id=user.id,
        email=user.email,
        email_verified=True,
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
    )


@router.post("/refresh", response_model=TokenPairOut)
async def refresh(
    response: Response,
    refresh_token_repo: RefreshTokenRepoDep,
    config: AuthConfigDep,
    payload: RefreshIn | None = None,
    refresh_token: str | None = Cookie(default=None),
) -> TokenPairOut:
    """Rotate the refresh token for a new pair.

    Reuse of an already-used token revokes its whole family. Accepts the
    refresh token from either the request body or the cookie (body takes
    priority) so both browser and non-browser clients can call it.
    """
    raw_refresh_token = (payload.refresh_token if payload else None) or refresh_token
    if raw_refresh_token is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    try:
        pair = await service.rotate_refresh_token(
            refresh_token_repo, raw_refresh_token, config=config, now=datetime.now(UTC)
        )
    except (InvalidRefreshToken, RefreshTokenExpired, RefreshTokenReuseDetected) as exc:
        response.set_cookie(**clear_access_token_cookie(config=config))
        response.set_cookie(**clear_refresh_token_cookie(config=config))
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Not authenticated") from exc

    _set_token_cookies(response, pair, config=config)
    return TokenPairOut(access_token=pair.access_token, refresh_token=pair.refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    refresh_token_repo: RefreshTokenRepoDep,
    config: AuthConfigDep,
    payload: LogoutIn | None = None,
    refresh_token: str | None = Cookie(default=None),
) -> None:
    """Revoke the current session's refresh token family and clear both cookies."""
    raw_refresh_token = (payload.refresh_token if payload else None) or refresh_token
    if raw_refresh_token is not None:
        await service.logout(refresh_token_repo, raw_refresh_token, now=datetime.now(UTC))

    response.set_cookie(**clear_access_token_cookie(config=config))
    response.set_cookie(**clear_refresh_token_cookie(config=config))


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUserDep) -> UserOut:
    """Return the current user, resolved from the access token (cookie or bearer)."""
    return UserOut(id=user.id, email=user.email, email_verified=user.email_verified_at is not None)


# TODO: remove these hardcoded HTML responses once the frontend redirect lands.
_CONFIRM_EMAIL_SUCCESS_HTML = (
    "<html><body><h1>Email confirmed</h1><p>Your account is now active.</p></body></html>"
)
_CONFIRM_EMAIL_ERROR_HTML = (
    "<html><body><h1>Link expired</h1>"
    "<p>This confirmation link is invalid or has expired.</p></body></html>"
)


# TODO: redirect to the frontend instead of returning HTML directly, once it exists.
@router.get("/confirm-email", response_class=HTMLResponse, include_in_schema=False)
async def confirm_email_link(
    token_repo: EmailVerificationTokenRepoDep,
    user_repo: UserRepoDep,
    token: str,
) -> HTMLResponse:
    """Confirm email from the link sent by mail.

    Returns an HTML page directly — there's no frontend route for this yet.
    """
    try:
        await service.confirm_email(token_repo, user_repo, token, now=datetime.now(UTC))
    except InvalidVerificationToken, VerificationTokenExpired:
        return HTMLResponse(_CONFIRM_EMAIL_ERROR_HTML, status_code=status.HTTP_400_BAD_REQUEST)
    return HTMLResponse(_CONFIRM_EMAIL_SUCCESS_HTML)


@router.post("/confirm-email", status_code=status.HTTP_204_NO_CONTENT)
async def confirm_email(
    payload: ConfirmEmailIn,
    token_repo: EmailVerificationTokenRepoDep,
    user_repo: UserRepoDep,
) -> None:
    """Confirm email via a JSON request, for a frontend client instead of the emailed link."""
    await service.confirm_email(token_repo, user_repo, payload.token, now=datetime.now(UTC))


@router.post(
    "/resend-verification",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(rate_limit("3/minute"))],
)
async def resend_verification(
    payload: ResendVerificationIn,
    token_repo: EmailVerificationTokenRepoDep,
    user_repo: UserRepoDep,
    outbox_repo: EmailOutboxRepoDep,
    config: AuthConfigDep,
) -> None:
    """Re-queue the verification email.

    Always returns 204, whether or not the email is registered/unverified.
    """
    entry = await service.resend_verification_email(
        token_repo,
        user_repo,
        outbox_repo,
        email=payload.email,
        config=config,
        now=datetime.now(UTC),
    )
    if entry is not None:
        await _queue_dispatch(str(entry.id))


@router.post(
    "/forgot-password",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(rate_limit("3/minute"))],
)
async def forgot_password(
    payload: ForgotPasswordIn,
    reset_token_repo: PasswordResetTokenRepoDep,
    user_repo: UserRepoDep,
    outbox_repo: EmailOutboxRepoDep,
    config: AuthConfigDep,
) -> None:
    """Start a password reset.

    Always returns 204 with an empty body, whether or not the address belongs to
    a registered, verified account — identical response body, status, and (within
    `AUTH_FORGOT_PASSWORD_RESPONSE_FLOOR`) timing, so it can't be used to discover
    which addresses have accounts.
    """
    async with _response_floor(config.FORGOT_PASSWORD_RESPONSE_FLOOR):
        entry = await service.request_password_reset(
            reset_token_repo,
            user_repo,
            outbox_repo,
            email=payload.email,
            config=config,
            now=datetime.now(UTC),
        )
        if entry is not None:
            await _queue_dispatch(str(entry.id))


@router.post(
    "/reset-password",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(rate_limit("5/minute"))],
)
async def reset_password(
    payload: ResetPasswordIn,
    reset_token_repo: PasswordResetTokenRepoDep,
    user_repo: UserRepoDep,
    refresh_token_repo: RefreshTokenRepoDep,
    config: AuthConfigDep,
    pwned_checker: PwnedPasswordCheckerDep,
) -> None:
    """Set a new password from a reset link's token."""
    now = datetime.now(UTC)
    await service.assert_reset_token_valid(reset_token_repo, payload.token, now=now)
    await _enforce_password_policy(payload.new_password, config=config, pwned_checker=pwned_checker)
    await service.reset_password(
        reset_token_repo,
        user_repo,
        refresh_token_repo,
        payload.token,
        new_password=payload.new_password,
        now=now,
    )
