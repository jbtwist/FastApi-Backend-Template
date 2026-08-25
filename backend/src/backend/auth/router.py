from datetime import UTC, datetime

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse
from redis_fastapi import rate_limit

from backend.auth import service
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
    RefreshTokenRepoDep,
    UserRepoDep,
)
from backend.auth.exceptions import (
    EmailAlreadyRegistered,
    EmailNotVerified,
    InvalidCredentials,
    InvalidRefreshToken,
    InvalidVerificationToken,
    RefreshTokenExpired,
    RefreshTokenReuseDetected,
    VerificationTokenExpired,
)
from backend.auth.schemas import (
    ConfirmEmailIn,
    LoginIn,
    LoginOut,
    LogoutIn,
    RefreshIn,
    RegisterIn,
    ResendVerificationIn,
    TokenPairOut,
    UserOut,
)
from backend.mail.dependencies import EmailOutboxRepoDep
from backend.mail.tasks import dispatch_verification_email

router = APIRouter(prefix="/auth", tags=["auth"])


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
) -> UserOut:
    try:
        user = await service.register_user(
            user_repo, email=payload.email, password=payload.password
        )
    except EmailAlreadyRegistered as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Email already registered") from exc

    entry = await service.queue_verification_email(
        token_repo, outbox_repo, user, config=config, now=datetime.now(UTC)
    )
    await run_in_threadpool(dispatch_verification_email.delay, str(entry.id))
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
    try:
        user = await service.authenticate_user(
            user_repo, email=payload.email, password=payload.password
        )
    except InvalidCredentials as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials") from exc
    except EmailNotVerified as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Email not verified") from exc

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
    raw_refresh_token = (payload.refresh_token if payload else None) or refresh_token
    if raw_refresh_token is not None:
        await service.logout(refresh_token_repo, raw_refresh_token, now=datetime.now(UTC))

    response.set_cookie(**clear_access_token_cookie(config=config))
    response.set_cookie(**clear_refresh_token_cookie(config=config))


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUserDep) -> UserOut:
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
    try:
        await service.confirm_email(token_repo, user_repo, token, now=datetime.now(UTC))
    except (InvalidVerificationToken, VerificationTokenExpired):
        return HTMLResponse(_CONFIRM_EMAIL_ERROR_HTML, status_code=status.HTTP_400_BAD_REQUEST)
    return HTMLResponse(_CONFIRM_EMAIL_SUCCESS_HTML)


@router.post("/confirm-email", status_code=status.HTTP_204_NO_CONTENT)
async def confirm_email(
    payload: ConfirmEmailIn,
    token_repo: EmailVerificationTokenRepoDep,
    user_repo: UserRepoDep,
) -> None:
    try:
        await service.confirm_email(token_repo, user_repo, payload.token, now=datetime.now(UTC))
    except (InvalidVerificationToken, VerificationTokenExpired) as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="Invalid or expired verification token"
        ) from exc


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
    entry = await service.resend_verification_email(
        token_repo,
        user_repo,
        outbox_repo,
        email=payload.email,
        config=config,
        now=datetime.now(UTC),
    )
    if entry is not None:
        await run_in_threadpool(dispatch_verification_email.delay, str(entry.id))
