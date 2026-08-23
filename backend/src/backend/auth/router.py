from datetime import UTC, datetime

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
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
    RefreshTokenRepoDep,
    UserRepoDep,
)
from backend.auth.exceptions import (
    EmailAlreadyRegistered,
    InvalidCredentials,
    InvalidRefreshToken,
    RefreshTokenExpired,
    RefreshTokenReuseDetected,
)
from backend.auth.schemas import (
    LoginIn,
    LoginOut,
    LogoutIn,
    RefreshIn,
    RegisterIn,
    TokenPairOut,
    UserOut,
)

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
async def register(payload: RegisterIn, user_repo: UserRepoDep) -> UserOut:
    try:
        user = await service.register_user(
            user_repo, email=payload.email, password=payload.password
        )
    except EmailAlreadyRegistered as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Email already registered") from exc

    return UserOut(id=user.id, email=user.email)


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

    pair = await service.issue_token_pair(
        refresh_token_repo, user, config=config, now=datetime.now(UTC)
    )
    _set_token_cookies(response, pair, config=config)
    return LoginOut(
        id=user.id,
        email=user.email,
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
    return UserOut(id=user.id, email=user.email)
