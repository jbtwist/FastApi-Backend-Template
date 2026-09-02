import uuid
from collections.abc import AsyncIterator
from typing import Annotated

import httpx
from fastapi import Cookie, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.auth.config import AuthConfig, auth_settings
from backend.auth.exceptions import AccessTokenExpired, InvalidAccessToken
from backend.auth.models import User
from backend.auth.password_policy import HIBPPwnedPasswordChecker, PwnedPasswordChecker
from backend.auth.repository import (
    SqlEmailVerificationTokenRepository,
    SqlPasswordResetTokenRepository,
    SqlRefreshTokenRepository,
    SqlUserRepository,
)
from backend.auth.security import decode_access_token
from backend.database import DbDep


def get_auth_config() -> AuthConfig:
    return auth_settings


AuthConfigDep = Annotated[AuthConfig, Depends(get_auth_config)]


def get_user_repo(db: DbDep) -> SqlUserRepository:
    return SqlUserRepository(db)


def get_refresh_token_repo(db: DbDep) -> SqlRefreshTokenRepository:
    return SqlRefreshTokenRepository(db)


def get_email_verification_token_repo(db: DbDep) -> SqlEmailVerificationTokenRepository:
    return SqlEmailVerificationTokenRepository(db)


def get_password_reset_token_repo(db: DbDep) -> SqlPasswordResetTokenRepository:
    return SqlPasswordResetTokenRepository(db)


async def get_pwned_password_checker() -> AsyncIterator[PwnedPasswordChecker]:
    """A HIBP breach checker backed by a per-request httpx client.

    Register/reset are the only callers, so a fresh connection per call is cheap
    and it sidesteps the lifecycle problems of a module-level client. HIBP asks
    callers to send a User-Agent; Add-Padding hides the true bucket size.
    """
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(2.0),
        headers={"User-Agent": "todoapp-backend", "Add-Padding": "true"},
    ) as client:
        yield HIBPPwnedPasswordChecker(client=client)


UserRepoDep = Annotated[SqlUserRepository, Depends(get_user_repo)]
RefreshTokenRepoDep = Annotated[SqlRefreshTokenRepository, Depends(get_refresh_token_repo)]
EmailVerificationTokenRepoDep = Annotated[
    SqlEmailVerificationTokenRepository, Depends(get_email_verification_token_repo)
]
PasswordResetTokenRepoDep = Annotated[
    SqlPasswordResetTokenRepository, Depends(get_password_reset_token_repo)
]
PwnedPasswordCheckerDep = Annotated[PwnedPasswordChecker, Depends(get_pwned_password_checker)]

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    user_repo: UserRepoDep,
    config: AuthConfigDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)] = None,
    access_token: Annotated[str | None, Cookie()] = None,
) -> User:
    token = credentials.credentials if credentials is not None else access_token
    if token is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    try:
        payload = decode_access_token(token, config=config)
    except (InvalidAccessToken, AccessTokenExpired) as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Not authenticated") from exc

    user = await user_repo.get_by_id(uuid.UUID(payload["sub"]))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    return user


CurrentUserDep = Annotated[User, Depends(get_current_user)]
