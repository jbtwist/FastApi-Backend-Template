from fastapi import FastAPI
from redis_fastapi import FastAPIRedis

from backend import models  # noqa: F401
from backend.auth.router import router as auth_router

app = FastAPI(title="GTD Backend")
FastAPIRedis(app).lifespan().rate_limiting()
app.include_router(auth_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
