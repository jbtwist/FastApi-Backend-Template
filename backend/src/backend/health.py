"""Liveness and readiness probes.

`/health` answers from the process alone, and is the one a load balancer
probes: a check that fails whenever a dependency is slow would deregister every
replica at once, turning a brief Postgres blip into a total outage. `/readyz`
reports this replica's view of Postgres and Redis, for deploy smoke tests,
dashboards and operators.

Every check here reports an unreachable dependency as `False` rather than
raising, so one dead service cannot turn the probe itself into a 500.
"""

import asyncio
from dataclasses import dataclass

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


@dataclass(frozen=True)
class ReadinessReport:
    """One readiness probe's outcome, per dependency."""

    database: bool
    redis: bool

    @property
    def ready(self) -> bool:
        """Whether every dependency answered."""
        return self.database and self.redis


async def check_database(engine: AsyncEngine) -> bool:
    """Whether Postgres answers a trivial query on a pooled connection."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        return False
    return True


async def check_redis(redis_client: Redis) -> bool:
    """Whether Redis answers `PING`."""
    try:
        await redis_client.ping()
    except Exception:
        return False
    return True


async def check_readiness(*, engine: AsyncEngine, redis_client: Redis) -> ReadinessReport:
    """Probe both dependencies, reporting each one separately."""
    database, redis = await asyncio.gather(check_database(engine), check_redis(redis_client))
    return ReadinessReport(database=database, redis=redis)
