"""Real-Postgres tests for `SqlEmailOutboxRepository`.

Most tests run inside a transaction that the `db` fixture rolls back. The
claim race needs two independent connections committing for real, so it builds
its own sessions on the engine and cleans up after itself.
"""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from backend.auth.models import User
from backend.mail.models import EmailOutboxEntry, EmailOutboxStatus
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


async def test_claiming_a_pending_entry_returns_it_as_sending(repo, user):
    entry = await _entry(repo, user, created_at=NOW)

    claimed = await repo.claim_for_send(entry.id, now=NOW)

    assert claimed is not None
    assert claimed.id == entry.id
    assert claimed.status == EmailOutboxStatus.SENDING


async def test_claiming_an_already_claimed_entry_returns_none(repo, user):
    entry = await _entry(repo, user, created_at=NOW)
    await repo.claim_for_send(entry.id, now=NOW)

    assert await repo.claim_for_send(entry.id, now=NOW) is None


@pytest.mark.parametrize("terminal", ["sent", "dead"])
async def test_a_terminal_entry_cannot_be_claimed(repo, user, terminal):
    entry = await _entry(repo, user, created_at=NOW)
    if terminal == "sent":
        await repo.mark_sent(entry.id, sent_at=NOW)
    else:
        await repo.mark_dead(entry.id, failed_at=NOW)

    assert await repo.claim_for_send(entry.id, now=NOW) is None


async def test_a_stale_claim_can_be_taken_over(repo, user):
    entry = await _entry(repo, user, created_at=NOW - timedelta(hours=1))
    await repo.claim_for_send(entry.id, now=NOW - timedelta(minutes=30))

    reclaimed = await repo.claim_for_send(
        entry.id, now=NOW, sending_stale_before=NOW - timedelta(minutes=5)
    )

    assert reclaimed is not None


async def test_a_fresh_claim_is_not_taken_over(repo, user):
    entry = await _entry(repo, user, created_at=NOW)
    await repo.claim_for_send(entry.id, now=NOW)

    reclaimed = await repo.claim_for_send(
        entry.id, now=NOW, sending_stale_before=NOW - timedelta(minutes=5)
    )

    assert reclaimed is None


async def test_an_abandoned_claim_is_listed_as_stale(repo, user):
    entry = await _entry(repo, user, created_at=NOW - timedelta(hours=1))
    await repo.claim_for_send(entry.id, now=NOW - timedelta(minutes=30))

    stale = await repo.list_stale_pending(
        unattempted_before=UNATTEMPTED_BEFORE,
        attempted_before=ATTEMPTED_BEFORE,
        claimed_before=NOW - timedelta(minutes=5),
    )

    assert {e.id for e in stale} == {entry.id}


async def test_a_fresh_claim_is_not_listed_as_stale(repo, user):
    entry = await _entry(repo, user, created_at=NOW - timedelta(hours=1))
    await repo.claim_for_send(entry.id, now=NOW)

    stale = await repo.list_stale_pending(
        unattempted_before=UNATTEMPTED_BEFORE,
        attempted_before=ATTEMPTED_BEFORE,
        claimed_before=NOW - timedelta(minutes=5),
    )

    assert {e.id for e in stale} == set()


class TestClaimRace:
    """The claim is the only thing standing between two workers and two emails.

    A fake repository cannot prove this: it needs two real connections racing
    the same row, so the test commits for real and cleans up after itself.
    """

    @pytest_asyncio.fixture(loop_scope="session")
    async def sessions(self, _db_engine: AsyncEngine):
        return async_sessionmaker(_db_engine, expire_on_commit=False)

    @pytest_asyncio.fixture(loop_scope="session")
    async def committed_entry(self, sessions):
        async with sessions() as session, session.begin():
            user = User(email=f"{uuid.uuid4()}@example.com", password_hash="x")
            session.add(user)
            await session.flush()
            entry = await SqlEmailOutboxRepository(session).create(
                user_id=user.id, email=user.email, token="raw-token", created_at=NOW
            )
        yield entry
        async with sessions() as session, session.begin():
            await session.execute(
                delete(EmailOutboxEntry).where(EmailOutboxEntry.user_id == entry.user_id)
            )
            await session.execute(delete(User).where(User.id == entry.user_id))

    async def test_only_one_of_two_racing_claims_wins(self, sessions, committed_entry):
        async def claim():
            async with sessions() as session, session.begin():
                return await SqlEmailOutboxRepository(session).claim_for_send(
                    committed_entry.id, now=NOW
                )

        results = await asyncio.gather(claim(), claim())

        assert [r is None for r in results].count(False) == 1

    async def test_the_row_ends_up_claimed_exactly_once(self, sessions, committed_entry):
        async def claim():
            async with sessions() as session, session.begin():
                return await SqlEmailOutboxRepository(session).claim_for_send(
                    committed_entry.id, now=NOW
                )

        await asyncio.gather(claim(), claim())

        async with sessions() as session:
            stored = await session.get(EmailOutboxEntry, committed_entry.id)
            assert stored.status == EmailOutboxStatus.SENDING
