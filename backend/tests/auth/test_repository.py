"""Real-Postgres tests for the single-use-token repositories.

Everything else in tests/auth runs on in-memory fakes; these exercise the shared
`_SqlSingleUseTokenRepository` base and the refresh/reset extras against actual
SQL. Each test runs inside a transaction that the `db` fixture rolls back.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.models import User
from backend.auth.repository import (
    SqlEmailVerificationTokenRepository,
    SqlPasswordResetTokenRepository,
    SqlRefreshTokenRepository,
    SqlUserRepository,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")

NOW = datetime(2026, 1, 1, tzinfo=UTC)
LATER = NOW + timedelta(hours=1)


async def _add_user(db: AsyncSession) -> User:
    user = User(email=f"{uuid.uuid4()}@example.com", password_hash="x")
    db.add(user)
    await db.flush()
    return user


@pytest_asyncio.fixture(loop_scope="session")
async def user(db: AsyncSession) -> User:
    return await _add_user(db)


@pytest.fixture(params=["email_verification", "password_reset", "refresh"])
def token_case(request: pytest.FixtureRequest, db: AsyncSession):
    """(_SqlSingleUseTokenRepository, create(user_id, *, token_hash, expires_at))."""
    if request.param == "refresh":
        repo = SqlRefreshTokenRepository(db)

        async def create(user_id, *, token_hash, expires_at):
            return await repo.create(
                user_id=user_id,
                family_id=uuid.uuid4(),
                token_hash=token_hash,
                expires_at=expires_at,
            )
    else:
        repo = (
            SqlPasswordResetTokenRepository(db)
            if request.param == "password_reset"
            else SqlEmailVerificationTokenRepository(db)
        )

        async def create(user_id, *, token_hash, expires_at):
            return await repo.create(user_id=user_id, token_hash=token_hash, expires_at=expires_at)

    return repo, create


class TestSharedBehavior:
    async def test_create_then_get_by_hash_round_trips(self, token_case, user):
        repo, create = token_case
        row = await create(user.id, token_hash="hash-a", expires_at=LATER)

        found = await repo.get_by_hash("hash-a")

        assert found is not None
        assert found.id == row.id
        assert found.user_id == user.id
        assert found.used_at is None

    async def test_get_by_hash_miss_returns_none(self, token_case, user):
        repo, _ = token_case
        assert await repo.get_by_hash("absent") is None

    async def test_mark_used_succeeds_once_then_fails(self, token_case, user):
        repo, create = token_case
        row = await create(user.id, token_hash="hash-b", expires_at=LATER)

        assert await repo.mark_used(row.id, used_at=NOW) is True
        assert await repo.mark_used(row.id, used_at=NOW) is False


class TestSqlPasswordResetTokenRepository:
    async def test_invalidate_all_for_user_burns_only_unused_rows_of_that_user(
        self, db: AsyncSession
    ):
        repo = SqlPasswordResetTokenRepository(db)
        target = await _add_user(db)
        other = await _add_user(db)

        still_open = await repo.create(user_id=target.id, token_hash="open", expires_at=LATER)
        already_used = await repo.create(user_id=target.id, token_hash="used", expires_at=LATER)
        await repo.mark_used(already_used.id, used_at=NOW)
        untouched = await repo.create(user_id=other.id, token_hash="other", expires_at=LATER)

        await repo.invalidate_all_for_user(target.id, invalidated_at=LATER)
        await db.flush()
        db.expire_all()

        assert (await repo.get_by_hash("open")).used_at == LATER
        assert (await repo.get_by_hash("used")).used_at == NOW
        assert (await repo.get_by_hash("other")).used_at is None
        assert still_open.id != untouched.id


class TestSqlRefreshTokenRepository:
    async def test_revoke_family_only_revokes_that_family(self, db: AsyncSession, user: User):
        repo = SqlRefreshTokenRepository(db)
        family = uuid.uuid4()
        await repo.create(user_id=user.id, family_id=family, token_hash="in", expires_at=LATER)
        await repo.create(
            user_id=user.id, family_id=uuid.uuid4(), token_hash="out", expires_at=LATER
        )

        await repo.revoke_family(family, revoked_at=NOW)
        await db.flush()
        db.expire_all()

        assert (await repo.get_by_hash("in")).revoked_at == NOW
        assert (await repo.get_by_hash("out")).revoked_at is None

    async def test_revoke_all_for_user_revokes_every_open_token(self, db: AsyncSession, user: User):
        repo = SqlRefreshTokenRepository(db)
        await repo.create(user_id=user.id, family_id=uuid.uuid4(), token_hash="a", expires_at=LATER)
        await repo.create(user_id=user.id, family_id=uuid.uuid4(), token_hash="b", expires_at=LATER)

        await repo.revoke_all_for_user(user.id, revoked_at=NOW)
        await db.flush()
        db.expire_all()

        assert (await repo.get_by_hash("a")).revoked_at == NOW
        assert (await repo.get_by_hash("b")).revoked_at == NOW


async def test_a_row_write_is_logged_on_the_db_audit_logger(db, captured_records):
    """Row writes have a logger of their own, so their volume can be set apart."""
    await SqlUserRepository(db).create(email=f"{uuid.uuid4()}@example.com", password_hash="x")

    [record] = [record for record in captured_records if record.event == "db_write"]
    assert record.name == "backend.audit.db"
    assert record.audit_fields["table"] == "user"
