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
"""

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


async def get_db() -> AsyncSession:
    """Yield a session inside a transaction that commits when the request returns."""
    async with SessionFactory() as session, session.begin():
        yield session


DbDep = Annotated[AsyncSession, Depends(get_db)]

worker_engine = create_async_engine(str(settings.DATABASE_URL), poolclass=NullPool)
WorkerSessionFactory = async_sessionmaker(worker_engine, expire_on_commit=False)
