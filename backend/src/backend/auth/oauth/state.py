"""Where a sign-in attempt waits between `start` and the provider exchange.

Kept in Redis, not in process memory, so any API instance can finish an attempt
another one started.
"""

from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol

from redis.asyncio import Redis


@dataclass(frozen=True, slots=True)
class SignInAttempt:
    """One pending sign-in attempt, as stored under its `state`."""

    provider: str
    nonce: str
    redirect_target: str


class SignInStateStore(Protocol):
    async def save(self, state: str, attempt: SignInAttempt, *, ttl: timedelta) -> None:
        """Store `attempt` under `state` until `ttl` passes."""
        ...

    async def consume(self, state: str) -> SignInAttempt | None:
        """Remove and return the attempt stored under `state`; `None` if there is none.

        Atomic: of two concurrent calls for one `state`, at most one gets the attempt.
        """
        ...


class RedisSignInStateStore:
    """A `SignInStateStore` over Redis, one key per attempt: `oauth:state:{state}`.

    The key expires with the attempt, and `consume` is a single `GETDEL`, so an
    attempt is spent the moment it is read.
    """

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def save(self, state: str, attempt: SignInAttempt, *, ttl: timedelta) -> None:
        raise NotImplementedError

    async def consume(self, state: str) -> SignInAttempt | None:
        raise NotImplementedError
