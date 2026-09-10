"""Real-Postgres tests for the durability of stolen-refresh-token revocation.

`rotate_refresh_token` revokes the whole family when it is handed a token that
was already spent. `get_db` wraps each request in `session.begin()`, so that
revocation only reaches the database if the request ends without an exception —
which is why reuse is reported as a `ReuseDetected` return value and the
endpoint *returns* its 401 instead of raising one.

The fakes in `tests/auth/fakes.py` cannot express any of this: they hold state
in a dict, with no transaction to roll back, so reuse detection looks like it
works there whatever the real code does. Hence a real session here, opened and
closed the same way `get_db` opens and closes one.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from backend.auth import service
from backend.auth.config import AuthConfig
from backend.auth.exceptions import InvalidRefreshToken
from backend.auth.models import RefreshToken, User
from backend.auth.repository import SqlRefreshTokenRepository
from backend.auth.security import generate_opaque_token, hash_opaque_token

pytestmark = pytest.mark.asyncio(loop_scope="session")

NOW = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture
def session_factory(_db_engine: AsyncEngine) -> async_sessionmaker:
    """Sessions that really commit.

    The shared `db` fixture rolls its transaction back at teardown, which is
    the one thing these tests cannot have: what is under test is precisely
    which writes survive.
    """
    return async_sessionmaker(bind=_db_engine, expire_on_commit=False)


@pytest_asyncio.fixture(loop_scope="session")
async def user(session_factory: async_sessionmaker):
    """A committed user, and its refresh tokens, removed afterwards."""
    async with session_factory() as session, session.begin():
        row = User(email=f"{uuid.uuid4()}@example.com", password_hash="x")
        session.add(row)

    yield row

    async with session_factory() as session, session.begin():
        await session.execute(delete(RefreshToken).where(RefreshToken.user_id == row.id))
        await session.execute(delete(User).where(User.id == row.id))


@pytest_asyncio.fixture(loop_scope="session")
async def spent_and_successor(
    session_factory: async_sessionmaker, user: User, auth_config: AuthConfig
) -> tuple[str, str]:
    """A refresh token that has been rotated once, with the token that replaced it.

    Two committed transactions, one per request: the login that issued the
    first token, and the refresh that spent it.
    """
    raw_first = generate_opaque_token()
    async with session_factory() as session, session.begin():
        await SqlRefreshTokenRepository(session).create(
            user_id=user.id,
            family_id=uuid.uuid4(),
            token_hash=hash_opaque_token(raw_first),
            expires_at=NOW + auth_config.REFRESH_TOKEN_EXP,
        )

    async with session_factory() as session, session.begin():
        pair = await service.rotate_refresh_token(
            SqlRefreshTokenRepository(session), raw_first, config=auth_config, now=NOW
        )

    return raw_first, pair.refresh_token


async def _replay(
    session_factory: async_sessionmaker, raw_token: str, auth_config: AuthConfig
) -> None:
    """Present a spent token the way `/auth/refresh` does, transaction and all.

    The call returns instead of raising, so the block commits. Should reuse
    ever go back to raising, the exception escapes `session.begin()`, the
    revocation rolls back with it, and every assertion below fails.
    """
    async with session_factory() as session, session.begin():
        result = await service.rotate_refresh_token(
            SqlRefreshTokenRepository(session), raw_token, config=auth_config, now=NOW
        )
    assert isinstance(result, service.ReuseDetected)


async def test_replaying_a_spent_token_revokes_the_family_it_belongs_to(
    session_factory: async_sessionmaker,
    spent_and_successor: tuple[str, str],
    auth_config: AuthConfig,
) -> None:
    raw_spent, raw_successor = spent_and_successor

    await _replay(session_factory, raw_spent, auth_config)

    async with session_factory() as session, session.begin():
        successor = await SqlRefreshTokenRepository(session).get_by_hash(
            hash_opaque_token(raw_successor)
        )
    assert successor is not None
    assert successor.revoked_at is not None


async def test_the_stolen_chain_cannot_be_rotated_after_the_replay(
    session_factory: async_sessionmaker,
    spent_and_successor: tuple[str, str],
    auth_config: AuthConfig,
) -> None:
    """The thief's successor token must stop working, not just the replayed one."""
    raw_spent, raw_successor = spent_and_successor

    await _replay(session_factory, raw_spent, auth_config)

    with pytest.raises(InvalidRefreshToken):
        async with session_factory() as session, session.begin():
            await service.rotate_refresh_token(
                SqlRefreshTokenRepository(session),
                raw_successor,
                config=auth_config,
                now=NOW + timedelta(seconds=1),
            )
