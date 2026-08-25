import fakeredis.aioredis
import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from redis_fastapi import FastAPIRedis, rate_limit
from redis_fastapi import deps as redis_fastapi_deps


@pytest.fixture
async def client(monkeypatch: pytest.MonkeyPatch):
    fake_redis = fakeredis.aioredis.FakeRedis(server=fakeredis.aioredis.FakeServer())

    async def fake_get_async_redis(request):
        return fake_redis

    monkeypatch.setattr(redis_fastapi_deps, "get_async_redis", fake_get_async_redis)

    app = FastAPI()
    FastAPIRedis(app).lifespan().rate_limiting()

    @app.get("/limited", dependencies=[Depends(rate_limit("2/minute"))])
    async def limited() -> dict[str, bool]:
        return {"ok": True}

    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


class TestRateLimit:
    async def test_allows_requests_within_limit(self, client: AsyncClient):
        assert (await client.get("/limited")).status_code == 200
        assert (await client.get("/limited")).status_code == 200

    async def test_blocks_requests_over_limit(self, client: AsyncClient):
        await client.get("/limited")
        await client.get("/limited")

        blocked = await client.get("/limited")

        assert blocked.status_code == 429
        assert "Retry-After" in blocked.headers

    async def test_emits_rate_limit_headers(self, client: AsyncClient):
        response = await client.get("/limited")

        assert response.headers["X-RateLimit-Limit"] == "2"
        assert 0 <= int(response.headers["X-RateLimit-Remaining"]) < 2
