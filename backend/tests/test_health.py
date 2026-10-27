"""Tests for the liveness and readiness checks.

The happy paths run against the real test database and a `fakeredis` server.
The failure paths use fakes that raise, because what matters is that a probe
reports a dead dependency rather than propagating its exception.
"""

import fakeredis.aioredis
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from backend.health import ReadinessReport, check_database, check_readiness, check_redis

SESSION_LOOP = pytest.mark.asyncio(loop_scope="session")


class FailingRedis:
    """A client whose every command raises, as an unreachable server does."""

    def __init__(self, error: Exception) -> None:
        self._error = error

    async def ping(self) -> bool:
        raise self._error


class _FailingConnection:
    def __init__(self, error: Exception) -> None:
        self._error = error

    async def __aenter__(self):
        raise self._error

    async def __aexit__(self, *exc_info) -> bool:
        return False


class FailingEngine:
    """Stands in for an engine whose server is gone or whose pool is exhausted."""

    def __init__(self, error: Exception) -> None:
        self._error = error

    def connect(self) -> _FailingConnection:
        return _FailingConnection(self._error)


@pytest.fixture
def redis_client() -> fakeredis.aioredis.FakeRedis:
    return fakeredis.aioredis.FakeRedis(server=fakeredis.aioredis.FakeServer())


@pytest.fixture
def dead_redis() -> FailingRedis:
    return FailingRedis(ConnectionError("redis is unreachable"))


@pytest.fixture
def dead_engine() -> FailingEngine:
    return FailingEngine(TimeoutError("pool exhausted"))


class TestCheckDatabase:
    pytestmark = SESSION_LOOP

    async def test_a_reachable_database_passes(self, _db_engine: AsyncEngine):
        assert await check_database(_db_engine) is True

    async def test_an_unreachable_database_fails_without_raising(self, dead_engine):
        assert await check_database(dead_engine) is False


class TestCheckRedis:
    pytestmark = SESSION_LOOP

    async def test_a_reachable_redis_passes(self, redis_client):
        assert await check_redis(redis_client) is True

    async def test_an_unreachable_redis_fails_without_raising(self, dead_redis):
        assert await check_redis(dead_redis) is False


class TestReadinessReport:
    @pytest.mark.parametrize(
        "database,redis,expected",
        [(True, True, True), (True, False, False), (False, True, False), (False, False, False)],
    )
    def test_ready_requires_every_dependency(self, database, redis, expected):
        assert ReadinessReport(database=database, redis=redis).ready is expected


class TestCheckReadiness:
    pytestmark = SESSION_LOOP

    async def test_a_healthy_replica_is_ready(self, _db_engine: AsyncEngine, redis_client):
        report = await check_readiness(engine=_db_engine, redis_client=redis_client)

        assert report.ready is True

    async def test_a_dead_redis_is_reported_without_blaming_the_database(
        self, _db_engine: AsyncEngine, dead_redis
    ):
        report = await check_readiness(engine=_db_engine, redis_client=dead_redis)

        assert (report.ready, report.database, report.redis) == (False, True, False)

    async def test_a_dead_database_is_reported_without_blaming_redis(
        self, dead_engine, redis_client
    ):
        report = await check_readiness(engine=dead_engine, redis_client=redis_client)

        assert (report.ready, report.database, report.redis) == (False, False, True)

    async def test_both_dependencies_down_still_reports_rather_than_raises(
        self, dead_engine, dead_redis
    ):
        report = await check_readiness(engine=dead_engine, redis_client=dead_redis)

        assert (report.ready, report.database, report.redis) == (False, False, False)
