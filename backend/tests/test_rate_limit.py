import contextlib
import logging

import fakeredis.aioredis
import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from redis_fastapi import FastAPIRedis, rate_limit
from redis_fastapi import deps as redis_fastapi_deps
from redis_fastapi.ratelimit import RateLimitMiddleware

from backend.config import Settings, settings
from backend.rate_limit import enable_rate_limiting
from backend.rate_limit import rate_limit as switchable_rate_limit


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


@pytest.fixture
def build_client(monkeypatch: pytest.MonkeyPatch):
    """Build a client whose route goes through `backend.rate_limit.rate_limit`.

    The switch is read when the dependency is built, so the setting has to be
    patched before the route is declared — hence a factory rather than a plain
    fixture.
    """
    fake_redis = fakeredis.aioredis.FakeRedis(server=fakeredis.aioredis.FakeServer())

    async def fake_get_async_redis(request):
        return fake_redis

    monkeypatch.setattr(redis_fastapi_deps, "get_async_redis", fake_get_async_redis)

    @contextlib.asynccontextmanager
    async def _build(*, enabled: bool):
        monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", enabled)

        app = FastAPI()
        FastAPIRedis(app).lifespan().rate_limiting()

        @app.get("/switched", dependencies=[Depends(switchable_rate_limit("2/minute"))])
        async def switched() -> dict[str, bool]:
            return {"ok": True}

        transport = ASGITransport(app=app)
        async with app.router.lifespan_context(app):
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                yield ac

    return _build


class TestRateLimitSwitch:
    async def test_enabled_by_default(self):
        assert Settings.model_fields["RATE_LIMIT_ENABLED"].default is True

    async def test_enforces_the_limit_while_enabled(self, build_client):
        async with build_client(enabled=True) as client:
            await client.get("/switched")
            await client.get("/switched")

            assert (await client.get("/switched")).status_code == 429

    async def test_serves_every_request_while_disabled(self, build_client):
        async with build_client(enabled=False) as client:
            for _ in range(5):
                assert (await client.get("/switched")).status_code == 200

    async def test_disabled_never_touches_redis(self, build_client, monkeypatch):
        """A stress run should not need Redis up, nor contend on its pool."""
        async with build_client(enabled=False) as client:
            monkeypatch.setattr(
                redis_fastapi_deps,
                "get_async_redis",
                lambda request: pytest.fail("rate limiter reached Redis while disabled"),
            )

            assert (await client.get("/switched")).status_code == 200

    async def test_warns_once_when_the_route_is_built(self, caplog, monkeypatch):
        monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)

        with caplog.at_level(logging.WARNING, logger="backend.rate_limit"):
            switchable_rate_limit("2/minute")

        assert "rate limiting is DISABLED" in caplog.text

    async def test_stays_silent_per_request(self, build_client, caplog):
        """A warning per request would put a log write in the hot path."""
        async with build_client(enabled=False) as client:
            # Drop the one warning emitted while the route was being built.
            caplog.clear()
            with caplog.at_level(logging.WARNING, logger="backend.rate_limit"):
                for _ in range(3):
                    await client.get("/switched")

        assert caplog.text == ""

    async def test_passes_skip_when_through_to_the_library(self, monkeypatch):
        monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
        app = FastAPI()
        FastAPIRedis(app).lifespan().rate_limiting()

        @app.get(
            "/skipped",
            dependencies=[
                Depends(switchable_rate_limit("1/minute", skip_when=lambda _request: True))
            ],
        )
        async def skipped() -> dict[str, bool]:
            return {"ok": True}

        transport = ASGITransport(app=app)
        async with app.router.lifespan_context(app):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                for _ in range(3):
                    assert (await client.get("/skipped")).status_code == 200


class TestEnableRateLimiting:
    """The app-wide half of the switch: the library's middleware and handler."""

    def test_installs_the_library_middleware_while_enabled(self, monkeypatch):
        monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
        app = FastAPI()

        enable_rate_limiting(FastAPIRedis(app))

        assert any(m.cls is RateLimitMiddleware for m in app.user_middleware)

    def test_installs_nothing_while_disabled(self, monkeypatch):
        """So an app-wide REDIS_RATE_LIMIT_DEFAULT_LIMIT can't reach Redis either."""
        monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)
        app = FastAPI()

        enable_rate_limiting(FastAPIRedis(app))

        assert not any(m.cls is RateLimitMiddleware for m in app.user_middleware)
