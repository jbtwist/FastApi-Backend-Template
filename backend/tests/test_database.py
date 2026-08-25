from sqlalchemy.pool import NullPool

from backend.database import worker_engine


def test_worker_engine_uses_null_pool():
    """Regression: a pooled connection reused across asyncio.run() loops closes the loop."""
    assert isinstance(worker_engine.pool, NullPool)
