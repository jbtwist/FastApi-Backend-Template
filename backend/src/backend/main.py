from fastapi import FastAPI
from redis_fastapi import FastAPIRedis

from backend import models  # noqa: F401
from backend.auth.error_handlers import add_auth_error_handlers
from backend.auth.oauth.error_handlers import add_oauth_error_handlers
from backend.auth.router import router as auth_router
from backend.config import settings
from backend.cors import add_cors
from backend.log import CorrelationIdMiddleware, configure_logging
from backend.rate_limit import enable_rate_limiting

configure_logging(level=settings.LOG_LEVEL, log_format=settings.LOG_FORMAT)

app = FastAPI(title="GTD Backend")
enable_rate_limiting(FastAPIRedis(app).lifespan())
app.include_router(auth_router)
add_auth_error_handlers(app)
add_oauth_error_handlers(app)
app.add_middleware(CorrelationIdMiddleware)
add_cors(app, allowed_origins=settings.CORS_ALLOWED_ORIGINS)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
