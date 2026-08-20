from fastapi import FastAPI

app = FastAPI(title="GTD Backend")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
