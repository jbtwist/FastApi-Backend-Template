"""Httponly cookie parameters for the access/refresh tokens.

The refresh token cookie is scoped to `path="/auth"` so the browser only ever
sends it to auth endpoints, not on every request — the access token cookie
covers the whole app (`path="/"`) since it's needed on every authenticated
request.
"""

from typing import TypedDict

from backend.auth.config import AuthConfig


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
