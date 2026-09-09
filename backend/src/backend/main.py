from fastapi import FastAPI
from redis_fastapi import FastAPIRedis

from backend import models  # noqa: F401
from backend.auth.error_handlers import add_auth_error_handlers
from backend.auth.router import router as auth_router
from backend.config import settings
from backend.cors import add_cors

app = FastAPI(title="GTD Backend")
FastAPIRedis(app).lifespan().rate_limiting()
app.include_router(auth_router)
add_auth_error_handlers(app)
# Last, so CORS wraps the rate-limiting middleware and its 429s carry the headers.
add_cors(app, allowed_origins=settings.CORS_ALLOWED_ORIGINS)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
