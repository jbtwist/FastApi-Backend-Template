from functools import cache

from fastapi import FastAPI, Response, status
from redis.asyncio import Redis
from redis_fastapi import FastAPIRedis

from backend import models  # noqa: F401
from backend.auth.error_handlers import add_auth_error_handlers
from backend.auth.oauth.error_handlers import add_oauth_error_handlers
from backend.auth.router import router as auth_router
from backend.config import settings
from backend.cors import add_cors
from backend.database import engine
from backend.health import check_readiness
from backend.log import CorrelationIdMiddleware, configure_logging
from backend.rate_limit import enable_rate_limiting

configure_logging(
    level=settings.LOG_LEVEL,
    log_format=settings.LOG_FORMAT,
    instance_id=settings.INSTANCE_ID,
)

app = FastAPI(title="Backend Template")
enable_rate_limiting(FastAPIRedis(app).lifespan())
app.include_router(auth_router)
add_auth_error_handlers(app)
add_oauth_error_handlers(app)
app.add_middleware(CorrelationIdMiddleware, instance_id=settings.INSTANCE_ID)
add_cors(app, allowed_origins=settings.CORS_ALLOWED_ORIGINS)


@cache
def _readiness_probe_redis() -> Redis:
    """The readiness probe's own Redis client.

    The rate limiter's pool belongs to its lifespan and is not exposed as a
    client, so the probe opens its own. It reports whether Redis is reachable,
    not whether the application's pool has room.
    """
    return Redis.from_url(settings.REDIS_URL)


@app.get("/health")
async def health() -> dict[str, str]:
    """Whether this process is alive. Touches no dependency.

    The check a load balancer should probe: one that failed whenever Postgres
    or Redis was slow would pull every replica out of rotation at once.
    """
    return {"status": "ok"}


@app.get("/readyz")
async def readyz(response: Response) -> dict[str, bool]:
    """Whether this replica can serve: its Postgres and Redis both answer.

    `503` when either does not, so a deploy can wait for a replica to come up
    and a dashboard can show which dependency is at fault.
    """
    report = await check_readiness(engine=engine, redis_client=_readiness_probe_redis())
    if not report.ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"ready": report.ready, "database": report.database, "redis": report.redis}
