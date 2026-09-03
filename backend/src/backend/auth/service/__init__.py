"""Signup, login/session, and password-reset business logic."""

from backend.auth.service.login import (
    TokenPair,
    authenticate_user,
    issue_token_pair,
    logout,
    rotate_refresh_token,
)
from backend.auth.service.password_reset import (
    assert_reset_token_valid,
    request_password_reset,
    reset_password,
)
from backend.auth.service.signup import (
    confirm_email,
    ensure_email_available,
    queue_verification_email,
    register_user,
    resend_verification_email,
)

__all__ = [
    "TokenPair",
    "assert_reset_token_valid",
    "authenticate_user",
    "confirm_email",
    "ensure_email_available",
    "issue_token_pair",
    "logout",
    "queue_verification_email",
    "register_user",
    "request_password_reset",
    "resend_verification_email",
    "reset_password",
    "rotate_refresh_token",
]
