"""Httponly cookie parameters for the access/refresh tokens.

The refresh token cookie is scoped to `path="/auth"` so the browser only ever
sends it to auth endpoints, not on every request — the access token cookie
covers the whole app (`path="/"`) since it's needed on every authenticated
request.
"""

from typing import TypedDict

from fastapi import Response

from backend.auth.config import AuthConfig
from backend.auth.service.login import TokenPair


class CookieParams(TypedDict):
    key: str
    value: str
    max_age: int
    path: str
    httponly: bool
    secure: bool
    samesite: str


def access_token_cookie(access_token: str, *, config: AuthConfig) -> CookieParams:
    return CookieParams(
        key="access_token",
        value=access_token,
        max_age=int(config.ACCESS_TOKEN_EXP.total_seconds()),
        path="/",
        httponly=True,
        secure=config.COOKIE_SECURE,
        samesite="lax",
    )


def refresh_token_cookie(refresh_token: str, *, config: AuthConfig) -> CookieParams:
    return CookieParams(
        key="refresh_token",
        value=refresh_token,
        max_age=int(config.REFRESH_TOKEN_EXP.total_seconds()),
        path="/auth",
        httponly=True,
        secure=config.COOKIE_SECURE,
        samesite="lax",
    )


def clear_access_token_cookie(*, config: AuthConfig) -> CookieParams:
    cookie = access_token_cookie("", config=config)
    cookie["max_age"] = 0
    return cookie


def clear_refresh_token_cookie(*, config: AuthConfig) -> CookieParams:
    cookie = refresh_token_cookie("", config=config)
    cookie["max_age"] = 0
    return cookie


def set_token_cookies(response: Response, pair: TokenPair, *, config: AuthConfig) -> None:
    """Set both session cookies on `response`, as every sign-in path does."""
    response.set_cookie(**access_token_cookie(pair.access_token, config=config))
    response.set_cookie(**refresh_token_cookie(pair.refresh_token, config=config))
