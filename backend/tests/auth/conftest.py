from collections.abc import AsyncIterator
from datetime import timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend import models  # noqa: F401  register models on Base.metadata
from backend.auth.config import AuthConfig
from backend.config import settings
from backend.database import Base
from tests.auth.fakes import (
    FakeEmailVerificationTokenRepository,
    FakePasswordResetTokenRepository,
    FakeRefreshTokenRepository,
    FakeUserRepository,
)

TEST_JWT_SECRET = "test-secret-1234567890123456789012345678901234567890123456789012"


@pytest.fixture
def auth_config() -> AuthConfig:
    return AuthConfig(
        JWT_SECRET=TEST_JWT_SECRET,
        JWT_ALG="HS256",
        ACCESS_TOKEN_EXP=timedelta(minutes=15),
        REFRESH_TOKEN_EXP=timedelta(days=7),
        EMAIL_VERIFICATION_TOKEN_EXP=timedelta(hours=24),
        PASSWORD_RESET_TOKEN_EXP=timedelta(hours=1),
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
def password_reset_token_repo() -> FakePasswordResetTokenRepository:
    return FakePasswordResetTokenRepository()


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def _db_engine() -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(str(settings.DATABASE_URL))
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(loop_scope="session")
async def db(_db_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """A session wrapped in a transaction that is rolled back after each test."""
    conn = await _db_engine.connect()
    txn = await conn.begin()
    session = async_sessionmaker(bind=conn, expire_on_commit=False)()
    try:
        yield session
    finally:
        await session.close()
        await txn.rollback()
        await conn.close()
