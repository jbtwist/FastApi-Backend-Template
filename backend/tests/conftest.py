"""Fixtures shared by every domain's tests.

The database fixtures build a throwaway `<name>_test` database per run with the
real migrations, so tests see the schema production gets. `DATABASE_URL` itself
is never touched.
"""

import asyncio
import os
import subprocess
import sys
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import URL, make_url, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.config import settings
from backend.log import correlation_id
from tests.mail.fakes import FakeEmailOutboxRepository

BACKEND_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _isolated_correlation_id():
    """Start every test with no correlation id.

    Anything that seeds one, a task or a middleware, otherwise leaves it set for
    whatever runs next in the same context.
    """
    token = correlation_id.set(None)
    yield
    correlation_id.reset(token)


@pytest.fixture
def email_outbox_repo() -> FakeEmailOutboxRepository:
    return FakeEmailOutboxRepository()


def _test_database_url() -> URL:
    """`DATABASE_URL` with `_test` appended to the database name."""
    url = make_url(str(settings.DATABASE_URL))
    return url.set(database=f"{url.database}_test")


async def _recreate_database(url: URL, *, drop_only: bool = False) -> None:
    admin = create_async_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        async with admin.connect() as conn:
            await conn.execute(text(f'DROP DATABASE IF EXISTS "{url.database}" WITH (FORCE)'))
            if not drop_only:
                await conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    finally:
        await admin.dispose()


def _migrate(url: URL) -> None:
    """Build the schema with the real migrations, so tests see what production gets."""
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR,
        env={**os.environ, "DATABASE_URL": url.render_as_string(hide_password=False)},
        check=True,
        capture_output=True,
    )


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def _db_engine() -> AsyncIterator[AsyncEngine]:
    """An engine on a throwaway `<name>_test` database, created and migrated per test run."""
    url = _test_database_url()
    await _recreate_database(url)
    await asyncio.to_thread(_migrate, url)
    engine = create_async_engine(url)
    yield engine
    await engine.dispose()
    await _recreate_database(url, drop_only=True)


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
