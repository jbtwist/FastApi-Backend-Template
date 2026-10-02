import pytest
from pydantic import ValidationError
from sqlalchemy.pool import NullPool

from backend.config import Settings
from backend.database import build_engine, worker_engine

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

    def test_pool_size_rejects_zero(self):
        """SQLAlchemy reads `pool_size=0` as unbounded, which is never what an
        operator capping connections meant."""
        with pytest.raises(ValidationError):
            _settings(DB_POOL_SIZE=0)
