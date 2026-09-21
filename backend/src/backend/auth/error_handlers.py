"""Maps `AuthError` subclasses to their HTTP responses in one place.

Endpoints let domain exceptions propagate and the handlers here turn them into
JSON. An `AuthError` missing below reaches a 500, flagging the unmapped path.
"""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from backend.auth.exceptions import (
    AuthError,
    EmailNotVerified,
    InvalidCredentials,
    InvalidPasswordResetToken,
    InvalidVerificationToken,
    PasswordResetTokenExpired,
    VerificationTokenExpired,
)

_HTTP_BY_ERROR: dict[type[AuthError], tuple[int, str]] = {
    InvalidCredentials: (status.HTTP_401_UNAUTHORIZED, "Invalid credentials"),
    EmailNotVerified: (status.HTTP_403_FORBIDDEN, "Email not verified"),
    InvalidVerificationToken: (
        status.HTTP_400_BAD_REQUEST,
        "Invalid or expired verification token",
    ),
    VerificationTokenExpired: (
        status.HTTP_400_BAD_REQUEST,
        "Invalid or expired verification token",
    ),
    InvalidPasswordResetToken: (status.HTTP_400_BAD_REQUEST, "Invalid or expired reset token"),
    PasswordResetTokenExpired: (status.HTTP_400_BAD_REQUEST, "Invalid or expired reset token"),
}


async def _handle(request: Request, exc: AuthError) -> JSONResponse:
    status_code, detail = _HTTP_BY_ERROR[type(exc)]
    return JSONResponse({"detail": detail}, status_code=status_code)


def add_auth_error_handlers(app: FastAPI) -> None:
    for exc_type in _HTTP_BY_ERROR:
        app.add_exception_handler(exc_type, _handle)
