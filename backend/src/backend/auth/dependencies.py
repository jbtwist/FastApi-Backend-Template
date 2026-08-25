import uuid
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.auth.config import AuthConfig, auth_settings
from backend.auth.exceptions import AccessTokenExpired, InvalidAccessToken
from backend.auth.models import User
from backend.auth.repository import (
    SqlEmailVerificationTokenRepository,
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


UserRepoDep = Annotated[SqlUserRepository, Depends(get_user_repo)]
RefreshTokenRepoDep = Annotated[SqlRefreshTokenRepository, Depends(get_refresh_token_repo)]
EmailVerificationTokenRepoDep = Annotated[
    SqlEmailVerificationTokenRepository, Depends(get_email_verification_token_repo)
]

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
