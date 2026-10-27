import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable

import pytest
import pytest_asyncio
from fastapi import FastAPI
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool

from backend.config import Settings
from backend.database import (
    DbDep,
    build_engine,
    call_after_commit,
    get_db,
    request_transaction,
    worker_engine,
)

TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/backend_template"


def _settings(**overrides) -> Settings:
    return Settings(DATABASE_URL=TEST_DATABASE_URL, **overrides)


def test_worker_engine_uses_null_pool():
    """Regression: a pooled connection reused across asyncio.run() loops closes the loop."""
    assert isinstance(worker_engine.pool, NullPool)


class TestConnectionPoolSizing:
    def test_pool_size_comes_from_settings(self):
        engine = build_engine(_settings(DB_POOL_SIZE=3, DB_MAX_OVERFLOW=7))

        assert engine.pool.size() == 3

    def test_max_overflow_comes_from_settings(self):
        engine = build_engine(_settings(DB_POOL_SIZE=3, DB_MAX_OVERFLOW=7))

        assert engine.pool._max_overflow == 7

    def test_defaults_are_conservative_enough_to_scale_out(self):
        """A replica's ceiling is DB_POOL_SIZE + DB_MAX_OVERFLOW; the product of that
        and the replica count has to stay under Postgres `max_connections`."""
        settings = _settings()

        assert settings.DB_POOL_SIZE + settings.DB_MAX_OVERFLOW <= 15

    def test_pool_size_rejects_a_negative_value(self):
        with pytest.raises(ValidationError):
            _settings(DB_POOL_SIZE=-1)

    def test_pool_timeout_comes_from_settings(self):
        engine = build_engine(_settings(DB_POOL_TIMEOUT=7.5))

        assert engine.pool._timeout == 7.5

    def test_default_pool_timeout_fails_rather_than_hangs(self):
        """SQLAlchemy's own default is 30 s, long enough that an exhausted pool
        reads as a hung service instead of a saturated one."""
        assert _settings().DB_POOL_TIMEOUT <= 5

    def test_pool_timeout_rejects_zero(self):
        with pytest.raises(ValidationError):
            _settings(DB_POOL_TIMEOUT=0)

    def test_pool_size_rejects_zero(self):
        """SQLAlchemy reads `pool_size=0` as unbounded, which is never what an
        operator capping connections meant."""
        with pytest.raises(ValidationError):
            _settings(DB_POOL_SIZE=0)


AFTER_COMMIT_EMAIL = "after-commit-{}@example.com"
SESSION_LOOP = pytest.mark.asyncio(loop_scope="session")


@pytest_asyncio.fixture(loop_scope="session")
async def committing_session_factory(
    _db_engine: AsyncEngine,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Sessions whose transactions really commit; the users they create are deleted after."""
    yield async_sessionmaker(_db_engine, expire_on_commit=False)
    async with _db_engine.begin() as conn:
        await conn.execute(text("""DELETE FROM "user" WHERE email LIKE 'after-commit-%'"""))


async def _insert_user(session: AsyncSession, email: str) -> None:
    await session.execute(
        text("""INSERT INTO "user" (id, email) VALUES (gen_random_uuid(), :email)"""),
        {"email": email},
    )


class HandlerFailed(Exception):
    pass


def _setter(event: asyncio.Event) -> Callable[[], Awaitable[None]]:
    async def set_event() -> None:
        event.set()

    return set_event


class TestCallAfterCommit:
    pytestmark = SESSION_LOOP

    async def test_a_callback_sees_what_the_transaction_committed(
        self, committing_session_factory, _db_engine
    ):
        """The reason it exists: a Celery worker must find the outbox row it was handed."""
        email = AFTER_COMMIT_EMAIL.format("sees")
        rows_seen: asyncio.Future[int] = asyncio.get_running_loop().create_future()

        async def count_rows() -> None:
            async with _db_engine.connect() as conn:
                query = text("""SELECT count(*) FROM "user" WHERE email = :email""")
                rows_seen.set_result(await conn.scalar(query, {"email": email}))

        async with request_transaction(committing_session_factory) as session:
            await _insert_user(session, email)
            call_after_commit(session, count_rows)

        assert await asyncio.wait_for(rows_seen, timeout=2) == 1

    async def test_a_rolled_back_transaction_runs_no_callback(self, committing_session_factory):
        calls: list[str] = []

        async def record() -> None:
            calls.append("ran")

        with pytest.raises(HandlerFailed):
            async with request_transaction(committing_session_factory) as session:
                call_after_commit(session, record)
                raise HandlerFailed
        await asyncio.sleep(0.05)

        assert calls == []

    async def test_the_transaction_returns_without_waiting_for_its_callbacks(
        self, committing_session_factory
    ):
        """Awaiting a broker call here would make forgot-password slower for registered
        addresses than for unknown ones, an enumeration timing oracle."""
        started, release = asyncio.Event(), asyncio.Event()

        async def blocks_until_released() -> None:
            started.set()
            await release.wait()

        async def run_request() -> None:
            async with request_transaction(committing_session_factory) as session:
                call_after_commit(session, blocks_until_released)

        await asyncio.wait_for(run_request(), timeout=2)
        await asyncio.wait_for(started.wait(), timeout=2)
        release.set()

    async def test_every_registered_callback_runs(self, committing_session_factory):
        done = {"first": asyncio.Event(), "second": asyncio.Event()}

        async with request_transaction(committing_session_factory) as session:
            call_after_commit(session, _setter(done["first"]))
            call_after_commit(session, _setter(done["second"]))

        await asyncio.wait_for(asyncio.gather(*(e.wait() for e in done.values())), timeout=2)

    async def test_a_failing_callback_is_logged_and_does_not_fail_the_request(
        self, committing_session_factory, caplog
    ):
        async def fails() -> None:
            raise ValueError("broker down")

        with caplog.at_level(logging.ERROR, logger="backend.database"):
            async with request_transaction(committing_session_factory) as session:
                call_after_commit(session, fails)
            for _ in range(100):
                if caplog.records:
                    break
                await asyncio.sleep(0.01)

        assert len(caplog.records) == 1
        assert caplog.records[0].exc_info[0] is ValueError


class TestRequestTransactionScope:
    async def test_commits_before_the_response_is_sent(self):
        """A 2xx must mean the writes are durable, so the commit cannot trail the response."""
        events: list[str] = []

        async def recording_get_db() -> AsyncIterator[AsyncSession]:
            yield AsyncSession()
            events.append("commit")

        app = FastAPI()

        @app.post("/write", status_code=204)
        async def write(db: DbDep) -> None:
            events.append("handler")

        app.dependency_overrides[get_db] = recording_get_db

        async def receive() -> dict:
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message: dict) -> None:
            events.append(message["type"])

        scope = {
            "type": "http",
            "method": "POST",
            "path": "/write",
            "headers": [],
            "query_string": b"",
            "http_version": "1.1",
            "scheme": "http",
            "server": ("test", 80),
            "client": ("test", 1),
            "root_path": "",
        }
        await app(scope, receive, send)

        assert events == ["handler", "commit", "http.response.start", "http.response.body"]
