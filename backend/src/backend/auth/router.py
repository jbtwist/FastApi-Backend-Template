"""`/auth` endpoints: registration, login, refresh, logout, email verification, password reset."""

from datetime import UTC, datetime
from functools import partial

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from fastapi.responses import JSONResponse

from backend.auth import service
from backend.auth.config import AuthConfig
from backend.auth.cookies import (
    clear_access_token_cookie,
    clear_refresh_token_cookie,
    set_token_cookies,
)
from backend.auth.dependencies import (
    AuthConfigDep,
    CurrentUserDep,
    EmailVerificationTokenRepoDep,
    PasswordResetTokenRepoDep,
    PwnedPasswordCheckerDep,
    RefreshTokenRepoDep,
    UserRepoDep,
    forgot_password_response_floor,
    register_response_floor,
)
from backend.auth.exceptions import (
    ConcurrentRefresh,
    InvalidRefreshToken,
    PasswordCompromised,
    PasswordTooLong,
    PasswordTooShort,
    RefreshTokenExpired,
)
from backend.auth.oauth.router import router as oauth_router
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
from backend.database import DbDep, call_after_commit
from backend.mail.dependencies import EmailOutboxRepoDep
from backend.mail.tasks import queue_dispatch_email
from backend.rate_limit import rate_limit

router = APIRouter(prefix="/auth", tags=["auth"])
router.include_router(oauth_router)


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


@router.post(
    "/register",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[
        Depends(rate_limit("5/minute")),
        Depends(register_response_floor, scope="function"),
    ],
)
async def register(
    payload: RegisterIn,
    user_repo: UserRepoDep,
    token_repo: EmailVerificationTokenRepoDep,
    outbox_repo: EmailOutboxRepoDep,
    config: AuthConfigDep,
    pwned_checker: PwnedPasswordCheckerDep,
    db: DbDep,
) -> None:
    """Register an account and queue its verification email.

    Enumeration-safe: an already-registered address is a silent no-op with a
    byte-identical `204` and the same response-floor timing. The password policy
    runs first and can `422`, but never consults the user table.
    """
    await _enforce_password_policy(payload.password, config=config, pwned_checker=pwned_checker)

    user = await service.register_user(user_repo, email=payload.email, password=payload.password)
    if user is None:
        return

    entry = await service.queue_verification_email(
        token_repo, outbox_repo, user, config=config, now=datetime.now(UTC)
    )
    call_after_commit(db, partial(queue_dispatch_email, str(entry.id)))


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
    set_token_cookies(response, pair, config=config)
    return LoginOut(
        id=user.id,
        email=user.email,
        email_verified=True,
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
    )


def _signed_out_response(*, config: AuthConfig) -> JSONResponse:
    """A 401 that also clears both token cookies.

    Returned, not raised: a raise discards the injected `Response` and rolls the
    transaction back, undoing the family revocation `ReuseDetected` carries.
    """
    response = JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED, content={"detail": "Not authenticated"}
    )
    response.set_cookie(**clear_access_token_cookie(config=config))
    response.set_cookie(**clear_refresh_token_cookie(config=config))
    return response


@router.post("/refresh", response_model=TokenPairOut)
async def refresh(
    response: Response,
    refresh_token_repo: RefreshTokenRepoDep,
    config: AuthConfigDep,
    payload: RefreshIn | None = None,
    refresh_token: str | None = Cookie(default=None),
) -> TokenPairOut | JSONResponse:
    """Rotate the refresh token for a new pair.

    Reuse of an already-used token revokes its whole family. Takes the token from
    the request body or the cookie, so both kinds of client can call it.

    A request that raced another refresh gets a `409`, with no cookies set or
    cleared: the winning request's cookies are still good, so the caller retries.
    """
    raw_refresh_token = (payload.refresh_token if payload else None) or refresh_token
    if raw_refresh_token is None:
        return _signed_out_response(config=config)

    try:
        result = await service.rotate_refresh_token(
            refresh_token_repo, raw_refresh_token, config=config, now=datetime.now(UTC)
        )
    except InvalidRefreshToken, RefreshTokenExpired:
        return _signed_out_response(config=config)
    except ConcurrentRefresh:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT, content={"detail": "Refresh already in progress"}
        )

    if isinstance(result, service.ReuseDetected):
        return _signed_out_response(config=config)

    set_token_cookies(response, result, config=config)
    return TokenPairOut(access_token=result.access_token, refresh_token=result.refresh_token)


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
    db: DbDep,
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
        call_after_commit(db, partial(queue_dispatch_email, str(entry.id)))


@router.post(
    "/forgot-password",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[
        Depends(rate_limit("3/minute")),
        Depends(forgot_password_response_floor, scope="function"),
    ],
)
async def forgot_password(
    payload: ForgotPasswordIn,
    reset_token_repo: PasswordResetTokenRepoDep,
    user_repo: UserRepoDep,
    outbox_repo: EmailOutboxRepoDep,
    config: AuthConfigDep,
    db: DbDep,
) -> None:
    """Start a password reset.

    Enumeration-safe: the same empty `204` whether or not the address belongs to a
    registered, verified account, within `FORGOT_PASSWORD_RESPONSE_FLOOR` timing.
    """
    entry = await service.request_password_reset(
        reset_token_repo,
        user_repo,
        outbox_repo,
        email=payload.email,
        config=config,
        now=datetime.now(UTC),
    )
    if entry is not None:
        call_after_commit(db, partial(queue_dispatch_email, str(entry.id)))


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
