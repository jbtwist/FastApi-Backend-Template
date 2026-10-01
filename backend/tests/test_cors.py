import fakeredis.aioredis
import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from redis_fastapi import FastAPIRedis, rate_limit
from redis_fastapi import deps as redis_fastapi_deps

from backend.config import Settings
from backend.cors import add_cors

ALLOWED_ORIGIN = "https://app.example"
OTHER_ORIGIN = "https://evil.example"
DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/backend_template"


def make_settings(**overrides: object) -> Settings:
    """Settings built in isolation from the developer's own `.env`."""
    return Settings(_env_file=None, DATABASE_URL=DATABASE_URL, **overrides)  # type: ignore[arg-type]


class TestCorsSettings:
    def test_splits_a_comma_separated_list(self):
        settings = make_settings(CORS_ALLOWED_ORIGINS=f"{ALLOWED_ORIGIN}, {OTHER_ORIGIN}")

        assert settings.CORS_ALLOWED_ORIGINS == [ALLOWED_ORIGIN, OTHER_ORIGIN]

    def test_ignores_blank_entries(self):
        settings = make_settings(CORS_ALLOWED_ORIGINS=f"{ALLOWED_ORIGIN},,  ,")

        assert settings.CORS_ALLOWED_ORIGINS == [ALLOWED_ORIGIN]

    def test_strips_a_trailing_slash(self):
        settings = make_settings(CORS_ALLOWED_ORIGINS=f"{ALLOWED_ORIGIN}/")

        assert settings.CORS_ALLOWED_ORIGINS == [ALLOWED_ORIGIN]

    @pytest.mark.parametrize("value", ["*", "*/", "*//", f"{ALLOWED_ORIGIN}, */"])
    def test_rejects_the_wildcard_origin(self, value):
        with pytest.raises(ValidationError, match="cannot be"):
            make_settings(CORS_ALLOWED_ORIGINS=value)

    def test_defaults_to_the_local_web_dev_server(self):
        assert make_settings().CORS_ALLOWED_ORIGINS == ["http://localhost:8081"]


@pytest.fixture
async def client(monkeypatch: pytest.MonkeyPatch):
    fake_redis = fakeredis.aioredis.FakeRedis(server=fakeredis.aioredis.FakeServer())

    async def fake_get_async_redis(request):
        return fake_redis

    monkeypatch.setattr(redis_fastapi_deps, "get_async_redis", fake_get_async_redis)

    app = FastAPI()
    FastAPIRedis(app).lifespan().rate_limiting()

    @app.post("/limited", dependencies=[Depends(rate_limit("1/minute"))])
    async def limited() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("unhandled")

    add_cors(app, allowed_origins=[ALLOWED_ORIGIN])

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


class TestCorsMiddleware:
    async def test_preflight_from_an_allowed_origin_is_accepted(self, client: AsyncClient):
        response = await client.options(
            "/limited",
            headers={
                "Origin": ALLOWED_ORIGIN,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )

        assert response.status_code == 200
        assert response.headers["Access-Control-Allow-Origin"] == ALLOWED_ORIGIN
        assert response.headers["Access-Control-Allow-Credentials"] == "true"
        assert "content-type" in response.headers["Access-Control-Allow-Headers"].lower()

    async def test_preflight_from_another_origin_gets_no_allow_header(self, client: AsyncClient):
        response = await client.options(
            "/limited",
            headers={"Origin": OTHER_ORIGIN, "Access-Control-Request-Method": "POST"},
        )

        assert "Access-Control-Allow-Origin" not in response.headers

    async def test_response_exposes_retry_after(self, client: AsyncClient):
        response = await client.post("/limited", headers={"Origin": ALLOWED_ORIGIN})

        assert response.headers["Access-Control-Allow-Origin"] == ALLOWED_ORIGIN
        assert "Retry-After" in response.headers["Access-Control-Expose-Headers"]

    async def test_rate_limited_response_still_carries_the_headers(self, client: AsyncClient):
        await client.post("/limited", headers={"Origin": ALLOWED_ORIGIN})

        blocked = await client.post("/limited", headers={"Origin": ALLOWED_ORIGIN})

        assert blocked.status_code == 429
        assert blocked.headers["Access-Control-Allow-Origin"] == ALLOWED_ORIGIN

    async def test_unhandled_error_still_carries_the_headers(self, client: AsyncClient):
        """Without them the browser hides the 500 and the client reports "offline"."""
        response = await client.get("/boom", headers={"Origin": ALLOWED_ORIGIN})

        assert response.status_code == 500
        assert response.headers["Access-Control-Allow-Origin"] == ALLOWED_ORIGIN
        assert response.headers["Access-Control-Allow-Credentials"] == "true"

    async def test_unhandled_error_still_reaches_the_server_log(self):
        """The error is answered inside CORS, then re-raised for the server to log."""
        app = FastAPI()

        @app.get("/boom")
        async def boom() -> None:
            raise RuntimeError("unhandled")

        add_cors(app, allowed_origins=[ALLOWED_ORIGIN])

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            with pytest.raises(RuntimeError, match="unhandled"):
                await ac.get("/boom", headers={"Origin": ALLOWED_ORIGIN})
