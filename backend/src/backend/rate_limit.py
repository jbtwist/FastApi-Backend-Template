"""Per-route rate limiting, with a switch for load testing.

Wraps `redis_fastapi.rate_limit` so routes keep declaring their real limit in
code while `RATE_LIMIT_ENABLED=false` stops it being enforced: a stress test
against an enforced limiter measures the limiter, not the application.

Import `rate_limit` from here, never from the library, and install the library
through `enable_rate_limiting`, going direct silently ignores the switch.
"""

import logging
from collections.abc import Awaitable, Callable

from redis_fastapi import FastAPIRedis
from redis_fastapi import rate_limit as _rate_limit
from redis_fastapi.rate import Rate

from backend.config import settings

logger = logging.getLogger(__name__)


async def _no_limit() -> None:
    """Stand-in dependency installed while the limiter is disabled."""


def enable_rate_limiting(redis: FastAPIRedis) -> None:
    """Set the library up on the app, unless `RATE_LIMIT_ENABLED` is false."""
    if settings.RATE_LIMIT_ENABLED:
        redis.rate_limiting()


def rate_limit(
    rate: str | Rate | tuple[int, int] | None = None,
    **kwargs: object,
) -> Callable[..., Awaitable[None]]:
    """Return the route dependency, honouring `RATE_LIMIT_ENABLED`.

    Args:
        rate: Limit spec, e.g. `"5/minute"`. Ignored while disabled.
        **kwargs: Any other `redis_fastapi.rate_limit` keyword.
    """
    if not settings.RATE_LIMIT_ENABLED:
        logger.warning(
            "rate limiting is DISABLED for %s (RATE_LIMIT_ENABLED=false) - "
            "load testing only, never production",
            rate,
        )
        return _no_limit
    return _rate_limit(rate, **kwargs)  # type: ignore[arg-type]
