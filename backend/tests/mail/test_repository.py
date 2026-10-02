"""Real-Postgres tests for `SqlEmailOutboxRepository.list_stale_pending`.

Each test runs inside a transaction that the `db` fixture rolls back.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.models import User
from backend.mail.repository import SqlEmailOutboxRepository

pytestmark = pytest.mark.asyncio(loop_scope="session")

NOW = datetime(2026, 1, 1, tzinfo=UTC)
UNATTEMPTED_BEFORE = NOW - timedelta(minutes=2)
ATTEMPTED_BEFORE = NOW - timedelta(minutes=20)


@pytest_asyncio.fixture(loop_scope="session")
async def user(db: AsyncSession) -> User:
    user = User(email=f"{uuid.uuid4()}@example.com", password_hash="x")
    db.add(user)
    await db.flush()
    return user


@pytest.fixture
def repo(db: AsyncSession) -> SqlEmailOutboxRepository:
    return SqlEmailOutboxRepository(db)


async def _entry(repo, user, *, created_at, attempted_at=None):
    entry = await repo.create(
        user_id=user.id, email=user.email, token="raw-token", created_at=created_at
    )
    if attempted_at is not None:
        await repo.mark_attempt_failed(entry.id, attempted_at=attempted_at)
    return entry


async def _stale_ids(repo) -> set[uuid.UUID]:
    stale = await repo.list_stale_pending(
        unattempted_before=UNATTEMPTED_BEFORE, attempted_before=ATTEMPTED_BEFORE
    )
    return {entry.id for entry in stale}


async def test_never_attempted_entry_follows_the_short_cutoff(repo, user):
    stale = await _entry(repo, user, created_at=NOW - timedelta(minutes=3))
    await _entry(repo, user, created_at=NOW - timedelta(minutes=1))

    assert await _stale_ids(repo) == {stale.id}


async def test_attempted_entry_follows_the_long_cutoff_on_its_last_attempt(repo, user):
    long_ago = NOW - timedelta(hours=2)
    stale = await _entry(repo, user, created_at=long_ago, attempted_at=NOW - timedelta(minutes=21))
    await _entry(repo, user, created_at=long_ago, attempted_at=NOW - timedelta(minutes=16))

    assert await _stale_ids(repo) == {stale.id}


async def test_excludes_sent_and_dead_entries(repo, user):
    long_ago = NOW - timedelta(hours=2)
    sent = await _entry(repo, user, created_at=long_ago)
    await repo.mark_sent(sent.id, sent_at=long_ago)
    dead = await _entry(repo, user, created_at=long_ago, attempted_at=long_ago)
    await repo.mark_dead(dead.id, failed_at=long_ago)

    assert await _stale_ids(repo) == set()
