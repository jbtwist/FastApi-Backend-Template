"""Per-route rate limiting, with a switch for load testing.

Wraps `redis_fastapi.rate_limit` so routes keep declaring their real limit in
code while `RATE_LIMIT_ENABLED=false` stops it being enforced. A stress
test against an enforced limiter measures the limiter, not the application:
past a few requests every response is a `429` served from Redis, so the numbers
say nothing about the code under test.

Import this instead of `redis_fastapi.rate_limit`, and install the library
through `enable_rate_limiting`; anything that goes to the library directly
silently ignores the switch.

Disabling removes a control that exists to blunt credential stuffing and email
bombing, so it defaults to on and says so loudly when it is off — see
`_no_limit`.
"""

import logging
from collections.abc import Awaitable, Callable

from redis_fastapi import FastAPIRedis
from redis_fastapi import rate_limit as _rate_limit
from redis_fastapi.rate import Rate

from backend.config import settings

logger = logging.getLogger(__name__)


async def _no_limit() -> None:
    """Stand-in dependency installed while the limiter is disabled.

    Deliberately silent. The warning is emitted once per route at import
    instead: logging per request would put a write in the hot path of the very
    load test the switch exists to keep clean.
    """


def enable_rate_limiting(redis: FastAPIRedis) -> None:
    """Set the library up on the app, unless `RATE_LIMIT_ENABLED` is false.

    `redis_fastapi`'s own setup call installs two things: the middleware and
    `429` handler that every `rate_limit` dependency below needs, and only
    when `REDIS_RATE_LIMIT_DEFAULT_LIMIT` is set in the environment,
    a single limit applied to every route in the app.

    Skipping the whole call while disabled is what keeps the switch honest: that
    app-wide limit is configured in the library's namespace, so nothing else
    here would turn it off.
    """
    if settings.RATE_LIMIT_ENABLED:
        redis.rate_limiting()


def rate_limit(
    rate: str | Rate | tuple[int, int] | None = None,
    **kwargs: object,
) -> Callable[..., Awaitable[None]]:
    """Return the route dependency, honouring `RATE_LIMIT_ENABLED`.

    While enabled, arguments pass through to `redis_fastapi.rate_limit`
    untouched, `skip_when` included.

    While disabled the library's dependency is not installed at all, rather than
    installed and told to skip. Skipping is not enough: the limiter takes the
    Redis backend as its own dependency, so FastAPI resolves a client before the
    skip predicate is consulted. A load test would then still need Redis up, and
    would still contend on its connection pool — precisely the confound the
    switch exists to remove.

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
