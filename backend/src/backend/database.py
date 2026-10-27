"""Database engines and the request-scoped session dependency.

Two engines: `engine` is pooled and serves requests, `worker_engine` uses
`NullPool` because each Celery task's `asyncio.run()` is a fresh event loop and
asyncpg connections are bound to the loop that opened them.

One API process holds at most `DB_POOL_SIZE + DB_MAX_OVERFLOW` connections, so
scaling out multiplies that by the replica count. Keep the product below
Postgres' `max_connections`, or put a connection pooler in front.

A request that finds the pool full waits `DB_POOL_TIMEOUT` seconds and then
fails, so saturation surfaces as errors that can be counted rather than as a
service that appears to have stalled.

Work that other processes must see the request's writes for, such as handing
an outbox row to a Celery worker, goes through `call_after_commit`, never
straight from the handler: the request transaction commits only after the
handler returns.
"""

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends
from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from backend.config import Settings, settings

logger = logging.getLogger(__name__)

_AFTER_COMMIT_KEY = "after_commit"
_running_after_commit: set[asyncio.Task[None]] = set()

POSTGRES_INDEXES_NAMING_CONVENTION = {
    "ix": "%(column_0_label)s_idx",
    "uq": "%(table_name)s_%(column_0_name)s_key",
    "ck": "%(table_name)s_%(constraint_name)s_check",
    "fk": "%(table_name)s_%(column_0_name)s_fkey",
    "pk": "%(table_name)s_pkey",
}
metadata = MetaData(naming_convention=POSTGRES_INDEXES_NAMING_CONVENTION)


class Base(DeclarativeBase):
    metadata = metadata


def build_engine(settings: Settings) -> AsyncEngine:
    """Build the request-path engine, pooled to `settings`' limits."""
    return create_async_engine(
        str(settings.DATABASE_URL),
        pool_pre_ping=True,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_timeout=settings.DB_POOL_TIMEOUT,
    )


engine = build_engine(settings)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


def call_after_commit(session: AsyncSession, callback: Callable[[], Awaitable[None]]) -> None:
    """Start `callback` once `session`'s request transaction commits.

    Never runs if the transaction rolls back. Started as a background task and
    not awaited, so it adds nothing to the response time; a failure is logged.
    """
    session.info.setdefault(_AFTER_COMMIT_KEY, []).append(callback)


async def _run_after_commit(callback: Callable[[], Awaitable[None]]) -> None:
    try:
        await callback()
    except Exception:
        logger.exception("after-commit callback %r failed", callback)


@asynccontextmanager
async def request_transaction(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Yield a session inside a transaction, then start its `call_after_commit` callbacks."""
    async with session_factory() as session:
        async with session.begin():
            yield session
        for callback in session.info.pop(_AFTER_COMMIT_KEY, []):
            task = asyncio.create_task(_run_after_commit(callback))
            _running_after_commit.add(task)
            task.add_done_callback(_running_after_commit.discard)


async def get_db() -> AsyncIterator[AsyncSession]:
    """Yield a session inside a transaction that commits when the request returns."""
    async with request_transaction(SessionFactory) as session:
        yield session


DbDep = Annotated[AsyncSession, Depends(get_db)]

worker_engine = create_async_engine(str(settings.DATABASE_URL), poolclass=NullPool)
WorkerSessionFactory = async_sessionmaker(worker_engine, expire_on_commit=False)
