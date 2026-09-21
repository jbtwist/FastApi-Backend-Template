"""HTTP-level tests for the `/auth/oauth` endpoints.

Resolution rules are covered in test_service.py; here we exercise the wiring:
status codes, cookies, the web callback's redirects and flags. A throwaway app
is built with fakeredis, a fake provider and in-memory repositories.
"""

from dataclasses import replace
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlsplit

import fakeredis.aioredis
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from redis_fastapi import FastAPIRedis
from redis_fastapi import deps as redis_fastapi_deps

from backend.auth import router as auth_router_module
from backend.auth import service as auth_service
from backend.auth.dependencies import get_auth_config, get_refresh_token_repo, get_user_repo
from backend.auth.error_handlers import add_auth_error_handlers
from backend.auth.oauth.dependencies import (
    get_enabled_providers,
    get_identity_repo,
    get_link_token_repo,
    get_oauth_config,
    get_state_store,
)
from backend.auth.oauth.error_handlers import add_oauth_error_handlers
from backend.config import settings
from backend.mail import tasks as mail_tasks
from backend.mail.dependencies import get_email_outbox_repo
from tests.auth.oauth.fakes import FakeOAuthProvider

FRONTEND = "https://app.todoapp.local"
NOW = datetime(2026, 1, 1, tzinfo=UTC)
FAR_FUTURE = datetime(2999, 1, 1, tzinfo=UTC)


@pytest.fixture
def provider() -> FakeOAuthProvider:
    return FakeOAuthProvider()


@pytest.fixture
def dispatch_calls() -> list[str]:
    return []


@pytest.fixture
async def client(
    monkeypatch,
    provider,
    state_store,
    user_repo,
    identity_repo,
    refresh_token_repo,
    link_token_repo,
    email_outbox_repo,
    auth_config,
    oauth_config,
    dispatch_calls,
):
    fake_redis = fakeredis.aioredis.FakeRedis(server=fakeredis.aioredis.FakeServer())

    async def fake_get_async_redis(request):
        return fake_redis

    monkeypatch.setattr(redis_fastapi_deps, "get_async_redis", fake_get_async_redis)
    monkeypatch.setattr(mail_tasks.dispatch_email, "delay", dispatch_calls.append)
    monkeypatch.setattr(settings, "FRONTEND_BASE_URL", FRONTEND)
    monkeypatch.setattr(settings, "API_BASE_URL", "https://api.todoapp.local")

    app = FastAPI()
    FastAPIRedis(app).lifespan().rate_limiting()
    app.include_router(auth_router_module.router)
    add_auth_error_handlers(app)
    add_oauth_error_handlers(app)
    app.dependency_overrides.update(
        {
            get_auth_config: lambda: auth_config,
            get_oauth_config: lambda: oauth_config,
            get_enabled_providers: lambda: {provider.name: provider},
            get_state_store: lambda: state_store,
            get_user_repo: lambda: user_repo,
            get_identity_repo: lambda: identity_repo,
            get_refresh_token_repo: lambda: refresh_token_repo,
            get_link_token_repo: lambda: link_token_repo,
            get_email_outbox_repo: lambda: email_outbox_repo,
        }
    )

    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


@pytest.fixture
async def verified_user(user_repo):
    user = await auth_service.register_user(
        user_repo, email="ada@example.com", password="s3cret-pw-long"
    )
    await user_repo.mark_email_verified(user.id, verified_at=NOW)
    return user


async def _native(client, provider, *, assertion: str | None = None):
    started = (await client.post("/auth/oauth/fake/start")).json()
    return await client.post(
        "/auth/oauth/fake/native",
        json={
            "state": started["state"],
            "assertion": assertion or provider.assertion_for(started["nonce"]),
        },
    )


async def _authorize(client, state_store, *, redirect_target: str = "/(app)") -> tuple[str, str]:
    response = await client.get(
        "/auth/oauth/fake/authorize", params={"redirect_target": redirect_target}
    )
    state = parse_qs(urlsplit(response.headers["location"]).query)["state"][0]
    return state, state_store.attempts[state].nonce


async def _callback(client, *, state: str, cookie_state: str | None = None, **params):
    return await client.get(
        "/auth/oauth/fake/callback",
        params={"state": state, **params},
        headers={"Cookie": f"oauth_state={cookie_state or state}"},
    )


def _flags(response) -> dict[str, str]:
    location = urlsplit(response.headers["location"])
    assert f"{location.scheme}://{location.netloc}{location.path}" == f"{FRONTEND}/sign-in"
    return {key: values[0] for key, values in parse_qs(location.query).items()}


class TestProviders:
    async def test_lists_the_enabled_providers(self, client):
        response = await client.get("/auth/oauth/providers")

        assert response.status_code == 200
        assert response.json() == {"providers": ["fake"]}


class TestStart:
    async def test_returns_a_state_a_nonce_and_their_lifetime(self, client):
        response = await client.post("/auth/oauth/fake/start")

        body = response.json()
        assert response.status_code == 200
        assert body["state"] and body["nonce"]
        assert body["expires_in"] == 600

    async def test_an_unknown_provider_is_404(self, client):
        response = await client.post("/auth/oauth/nope/start")

        assert response.status_code == 404


class TestNative:
    async def test_signs_in_with_cookies_and_tokens_like_login(self, client, provider):
        response = await _native(client, provider)

        body = response.json()
        assert response.status_code == 200
        assert body["email"] == "ada@example.com"
        assert body["email_verified"] is True
        assert body["access_token"] and body["refresh_token"]
        assert "access_token" in response.cookies
        assert "refresh_token" in response.cookies

    async def test_a_forged_assertion_is_401(self, client, provider):
        response = await _native(client, provider, assertion="fake:wrong-nonce")

        assert response.status_code == 401

    async def test_a_spent_state_is_401(self, client, provider):
        started = (await client.post("/auth/oauth/fake/start")).json()
        body = {"state": started["state"], "assertion": provider.assertion_for(started["nonce"])}
        await client.post("/auth/oauth/fake/native", json=body)

        response = await client.post("/auth/oauth/fake/native", json=body)

        assert response.status_code == 401

    async def test_an_unverified_provider_email_is_403(self, client, provider):
        provider.identity = replace(provider.identity, email_verified=False)

        response = await _native(client, provider)

        assert response.status_code == 403

    async def test_an_account_linked_elsewhere_is_409_naming_the_provider(
        self, client, provider, identity_repo, verified_user
    ):
        await identity_repo.create(
            user_id=verified_user.id,
            provider="second_fake",
            provider_subject="x",
            email_at_link=None,
            is_private_relay=False,
            display_name=None,
        )

        response = await _native(client, provider)

        assert response.status_code == 409
        assert response.json()["linked_provider"] == "second_fake"

    async def test_a_link_offer_is_202_and_dispatches_the_email(
        self, client, provider, dispatch_calls, verified_user
    ):
        response = await _native(client, provider)

        assert response.status_code == 202
        assert response.json() == {"status": "link_email_sent"}
        assert len(dispatch_calls) == 1
        assert "access_token" not in response.cookies


class TestAuthorize:
    async def test_redirects_to_the_provider_with_the_callback(self, client):
        response = await client.get("/auth/oauth/fake/authorize")

        location = urlsplit(response.headers["location"])
        query = parse_qs(location.query)
        assert response.status_code == 302
        assert location.netloc == "fake.example"
        assert query["redirect_uri"] == ["https://api.todoapp.local/auth/oauth/fake/callback"]

    async def test_binds_the_browser_with_an_httponly_state_cookie(self, client):
        response = await client.get("/auth/oauth/fake/authorize")

        state = parse_qs(urlsplit(response.headers["location"]).query)["state"][0]
        cookie = response.headers["set-cookie"]
        assert cookie.startswith(f"oauth_state={state};")
        assert "HttpOnly" in cookie
        assert "Path=/auth/oauth" in cookie


class TestCallback:
    async def test_signs_in_and_lands_on_the_redirect_target(self, client, provider, state_store):
        state, nonce = await _authorize(client, state_store, redirect_target="/(app)")

        response = await _callback(client, state=state, code=provider.assertion_for(nonce))

        assert response.status_code == 302
        assert response.headers["location"] == f"{FRONTEND}/(app)"
        cookies = response.headers.get_list("set-cookie")
        assert any(c.startswith("access_token=") for c in cookies)
        assert any(c.startswith("refresh_token=") for c in cookies)
        assert any(c.startswith('oauth_state="";') or "oauth_state=;" in c for c in cookies)

    async def test_a_state_not_matching_the_cookie_fails(self, client, provider, state_store):
        state, nonce = await _authorize(client, state_store)

        response = await _callback(
            client, state=state, cookie_state="someone-else", code=provider.assertion_for(nonce)
        )

        assert _flags(response) == {"oauth_error": "failed"}

    async def test_a_cancelled_consent_screen_is_flagged_cancelled(self, client, state_store):
        state, _ = await _authorize(client, state_store)

        response = await _callback(client, state=state, error="access_denied")

        assert _flags(response) == {"oauth_error": "cancelled"}

    async def test_an_unverified_provider_email_is_flagged(self, client, provider, state_store):
        provider.identity = replace(provider.identity, email_verified=False)
        state, nonce = await _authorize(client, state_store)

        response = await _callback(client, state=state, code=provider.assertion_for(nonce))

        assert _flags(response) == {"oauth_error": "email_not_verified_by_provider"}

    async def test_an_account_linked_elsewhere_is_flagged_with_the_provider(
        self, client, provider, state_store, identity_repo, verified_user
    ):
        await identity_repo.create(
            user_id=verified_user.id,
            provider="second_fake",
            provider_subject="x",
            email_at_link=None,
            is_private_relay=False,
            display_name=None,
        )
        state, nonce = await _authorize(client, state_store)

        response = await _callback(client, state=state, code=provider.assertion_for(nonce))

        assert _flags(response) == {
            "oauth_error": "email_linked_to_other_provider",
            "linked_provider": "second_fake",
        }

    async def test_a_link_offer_is_flagged_as_a_notice(
        self, client, provider, state_store, dispatch_calls, verified_user
    ):
        state, nonce = await _authorize(client, state_store)

        response = await _callback(client, state=state, code=provider.assertion_for(nonce))

        assert _flags(response) == {"oauth_notice": "link_email_sent"}
        assert len(dispatch_calls) == 1


class TestConfirmLink:
    async def test_redeems_an_emailed_token(
        self, client, provider, email_outbox_repo, verified_user
    ):
        await _native(client, provider)
        [entry] = await email_outbox_repo.list_stale_pending(older_than=FAR_FUTURE)

        response = await client.post("/auth/oauth/link/confirm", json={"token": entry.token})

        assert response.status_code == 204
        assert (await _native(client, provider)).status_code == 200

    async def test_an_unknown_token_is_400(self, client):
        response = await client.post("/auth/oauth/link/confirm", json={"token": "nope"})

        assert response.status_code == 400
