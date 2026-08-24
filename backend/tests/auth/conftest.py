from datetime import timedelta

import pytest

from backend.auth.config import AuthConfig
from tests.auth.fakes import (
    FakeEmailVerificationTokenRepository,
    FakeRefreshTokenRepository,
    FakeUserRepository,
)
from tests.mail.fakes import FakeEmailOutboxRepository

TEST_JWT_SECRET = "test-secret-1234567890123456789012345678901234567890123456789012"


@pytest.fixture
def auth_config() -> AuthConfig:
    return AuthConfig(
        JWT_SECRET=TEST_JWT_SECRET,
        JWT_ALG="HS256",
        ACCESS_TOKEN_EXP=timedelta(minutes=15),
        REFRESH_TOKEN_EXP=timedelta(days=7),
        EMAIL_VERIFICATION_TOKEN_EXP=timedelta(hours=24),
        COOKIE_SECURE=True,
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
def email_outbox_repo() -> FakeEmailOutboxRepository:
    return FakeEmailOutboxRepository()
