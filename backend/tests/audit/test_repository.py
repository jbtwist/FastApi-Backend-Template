"""Real-Postgres tests for the security-event repository.

Everything else in tests/audit runs on an in-memory fake; these exercise the
JSONB column, the nullable user link and the bulk delete against actual SQL.
Each test runs inside a transaction the `db` fixture rolls back.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from backend.audit.models import SecurityEvent, SecurityEventKind
from backend.audit.repository import SqlSecurityEventRepository
from backend.auth.models import User

pytestmark = pytest.mark.asyncio(loop_scope="session")

NOW = datetime(2026, 9, 23, 12, 0, tzinfo=UTC)


@pytest_asyncio.fixture(loop_scope="session")
async def user(db: AsyncSession) -> User:
    user = User(email=f"{uuid.uuid4()}@example.com", password_hash="x")
    db.add(user)
    await db.flush()
    return user


@pytest.fixture
def repo(db: AsyncSession) -> SqlSecurityEventRepository:
    return SqlSecurityEventRepository(db)


async def test_record_persists_a_row(repo, db, user):
    event = await repo.record(
        kind=SecurityEventKind.LOGIN_SUCCEEDED,
        user_id=user.id,
        correlation_id="req-abc",
        fields={"source": "web"},
        occurred_at=NOW,
    )
    await db.flush()
    assert event.id is not None
    assert event.kind == SecurityEventKind.LOGIN_SUCCEEDED
    assert event.user_id == user.id
    assert event.correlation_id == "req-abc"


async def test_jsonb_fields_round_trip(repo, db, user):
    family_id = str(uuid.uuid4())
    event = await repo.record(
        kind=SecurityEventKind.TOKEN_REUSE_DETECTED,
        user_id=user.id,
        correlation_id=None,
        fields={"reason": "spent_token_replayed", "family_id": family_id},
        occurred_at=NOW,
    )
    await db.flush()
    db.expunge_all()

    stored = await db.get(SecurityEvent, event.id)

    assert stored.fields == {"reason": "spent_token_replayed", "family_id": family_id}


async def test_occurred_at_round_trips_as_an_aware_timestamp(repo, db, user):
    event = await repo.record(
        kind=SecurityEventKind.LOGIN_SUCCEEDED,
        user_id=user.id,
        correlation_id=None,
        fields={},
        occurred_at=NOW,
    )
    await db.flush()
    db.expunge_all()

    stored = await db.get(SecurityEvent, event.id)

    assert stored.occurred_at == NOW


async def test_a_row_without_a_user_is_accepted(repo, db):
    """`login.failed` for an unknown address has nothing to attribute."""
    event = await repo.record(
        kind=SecurityEventKind.LOGIN_FAILED,
        user_id=None,
        correlation_id=None,
        fields={"reason": "invalid_credentials"},
        occurred_at=NOW,
    )
    await db.flush()
    assert event.user_id is None


async def test_delete_before_removes_only_older_rows(repo, db, user):
    for age in (timedelta(days=400), timedelta(days=200), timedelta(days=1)):
        await repo.record(
            kind=SecurityEventKind.LOGIN_SUCCEEDED,
            user_id=user.id,
            correlation_id=None,
            fields={},
            occurred_at=NOW - age,
        )
    await db.flush()

    deleted = await repo.delete_before(NOW - timedelta(days=180), batch_size=5000)

    assert deleted == 2


async def test_delete_before_on_an_empty_table_reports_zero(repo):
    assert await repo.delete_before(NOW, batch_size=5000) == 0


async def test_delete_before_stops_at_the_batch_size(repo, db, user):
    """One call is one bounded statement; draining the backlog is the caller's loop."""
    for days in range(10):
        await repo.record(
            kind=SecurityEventKind.LOGIN_SUCCEEDED,
            user_id=user.id,
            correlation_id=None,
            fields={},
            occurred_at=NOW - timedelta(days=300 + days),
        )
    await db.flush()

    assert await repo.delete_before(NOW - timedelta(days=180), batch_size=3) == 3
    assert await repo.delete_before(NOW - timedelta(days=180), batch_size=3) == 3
    assert await repo.delete_before(NOW - timedelta(days=180), batch_size=100) == 4
    assert await repo.delete_before(NOW - timedelta(days=180), batch_size=100) == 0


async def test_ids_are_time_ordered(repo, db, user):
    """uuid7, not uuid4: a random key scatters inserts across the index."""
    ids = []
    for _ in range(5):
        event = await repo.record(
            kind=SecurityEventKind.LOGIN_SUCCEEDED,
            user_id=user.id,
            correlation_id=None,
            fields={},
            occurred_at=NOW,
        )
        ids.append(event.id)
    await db.flush()

    assert ids == sorted(ids)


async def test_kind_is_not_indexed(db):
    """Eight distinct values across millions of rows never earns its write cost."""
    indexed = {tuple(index.columns.keys()) for index in SecurityEvent.__table__.indexes}

    assert ("kind",) not in indexed
    assert ("user_id", "occurred_at") in indexed
