from fastapi import FastAPI

from backend.auth.router import router as auth_router

app = FastAPI(title="GTD Backend")
app.include_router(auth_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
