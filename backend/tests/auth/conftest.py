from datetime import timedelta

import pytest

from backend.auth.config import AuthConfig
from tests.auth.fakes import (
    FakeEmailVerificationTokenRepository,
    FakePasswordResetTokenRepository,
    FakeRefreshTokenRepository,
    FakeUserRepository,
)

TEST_JWT_SECRET = "test-secret-1234567890123456789012345678901234567890123456789012"


@pytest.fixture
def auth_config_secure() -> bool:
    """Whether the app is serving over HTTPS. Overridden by tests that need plain HTTP."""
    return True


@pytest.fixture
def auth_config(auth_config_secure: bool) -> AuthConfig:
    return AuthConfig(
        JWT_SECRET=TEST_JWT_SECRET,
        JWT_ALG="HS256",
        ACCESS_TOKEN_EXP=timedelta(minutes=15),
        REFRESH_TOKEN_EXP=timedelta(days=7),
        EMAIL_VERIFICATION_TOKEN_EXP=timedelta(hours=24),
        PASSWORD_RESET_TOKEN_EXP=timedelta(hours=1),
        COOKIE_SECURE=auth_config_secure,
    )


@pytest.fixture
def user_repo() -> FakeUserRepository:
    return FakeUserRepository()


@pytest.fixture
def refresh_token_repo() -> FakeRefreshTokenRepository:
    return FakeRefreshTokenRepository()


@pytest.fixture
def email_verification_token_repo() -> FakeEmailVerificationTokenRepository:
    return FakeEmailVerificationTokenRepository()


@pytest.fixture
def password_reset_token_repo() -> FakePasswordResetTokenRepository:
    return FakePasswordResetTokenRepository()
