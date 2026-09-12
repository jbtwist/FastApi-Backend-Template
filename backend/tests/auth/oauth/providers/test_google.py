import logging
import time
from collections.abc import Callable
from datetime import timedelta
from typing import Any
from urllib.parse import parse_qsl, urlsplit

import httpx
import pytest
from pydantic import ValidationError

from backend.auth.oauth.contract import ProviderIdentity
from backend.auth.oauth.exceptions import (
    ProviderAssertionInvalid,
    ProviderNotConfigured,
    ProviderUnavailable,
)
from backend.auth.oauth.providers import google as google_module
from backend.auth.oauth.providers.google import (
    JWKS_CACHE_TTL,
    JWKS_REFRESH_COOLDOWN,
    GoogleConfig,
    GoogleProvider,
)
from backend.auth.oauth.registry import load_provider

GOOGLE_AUTHORIZATION_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"

WEB_CLIENT_ID = "web-client.apps.googleusercontent.com"
IOS_CLIENT_ID = "ios-client.apps.googleusercontent.com"
ANDROID_CLIENT_ID = "android-client.apps.googleusercontent.com"
OTHER_APP_CLIENT_ID = "another-app.apps.googleusercontent.com"
CLIENT_SECRET = "google-test-client-secret"
GOOGLE_SETTINGS = {
    "GOOGLE_CLIENT_ID_WEB": WEB_CLIENT_ID,
    "GOOGLE_CLIENT_ID_IOS": IOS_CLIENT_ID,
    "GOOGLE_CLIENT_ID_ANDROID": ANDROID_CLIENT_ID,
    "GOOGLE_CLIENT_SECRET": CLIENT_SECRET,
}

SUBJECT = "110169484474386276334"
NONCE = "nonce-issued-by-the-server"
REDIRECT_URI = "https://api.example/auth/oauth/google/callback"
ABSENT = object()


def google_claims(**overrides: Any) -> dict[str, Any]:
    """Claims of a genuine Google ID token for this app, issued just now.

    Override a claim to break it; pass `ABSENT` to leave it out.
    """
    now = int(time.time())
    claims = {
        "iss": "https://accounts.google.com",
        "aud": WEB_CLIENT_ID,
        "sub": SUBJECT,
        "email": "ada@example.com",
        "email_verified": True,
        "nonce": NONCE,
        "iat": now,
        "exp": now + 3600,
    }
    claims.update(overrides)
    return {name: value for name, value in claims.items() if value is not ABSENT}


async def sign_in(google: GoogleProvider, key, **claims: Any) -> ProviderIdentity:
    return await google.exchange_native(assertion=key.sign(google_claims(**claims)), nonce=NONCE)


def exception_text(exc: BaseException) -> str:
    """What an exception, and every exception chained behind it, says about itself."""
    parts: list[str] = []
    current: BaseException | None = exc
    while current is not None:
        parts += [str(current), repr(current)]
        current = current.__cause__ or current.__context__
    return "\n".join(parts)


def _unreachable(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("connection refused", request=request)


def _server_error(request: httpx.Request) -> httpx.Response:
    return httpx.Response(503)


def _not_json(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, text="<html>not json</html>")


def _no_keys(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"keys": []})


def _token_response(id_token: str) -> Callable[[httpx.Request], httpx.Response]:
    def answer(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "access_token": "unused-access-token",
                "expires_in": 3599,
                "id_token": id_token,
                "scope": "openid email",
                "token_type": "Bearer",
            },
        )

    return answer


class FakeGoogle:
    """Google's key and token endpoints, offline.

    The token endpoint answers with `answer_token_request`, which a test sets;
    until then it fails like an outage.
    """

    def __init__(self, jwks) -> None:
        self.jwks = jwks
        self.token_requests: list[httpx.Request] = []
        self.answer_token_request: Callable[[httpx.Request], httpx.Response] = _server_error

    def handle(self, request: httpx.Request) -> httpx.Response:
        endpoint = f"{request.url.scheme}://{request.url.host}{request.url.path}"
        if request.method == "GET" and endpoint == GOOGLE_JWKS_URL:
            return self.jwks.handle(request)
        if request.method == "POST" and endpoint == GOOGLE_TOKEN_URL:
            self.token_requests.append(request)
            return self.answer_token_request(request)
        return httpx.Response(404)


@pytest.fixture
def google_config() -> GoogleConfig:
    return GoogleConfig(**GOOGLE_SETTINGS, _env_file=None)


@pytest.fixture
def fake_google(jwks_endpoint) -> FakeGoogle:
    return FakeGoogle(jwks_endpoint)


@pytest.fixture
def google(google_config, fake_google, fake_clock) -> GoogleProvider:
    return GoogleProvider(
        google_config, transport=httpx.MockTransport(fake_google.handle), clock=fake_clock
    )


@pytest.fixture
def google_env(monkeypatch, tmp_path):
    """Every Google setting in the environment, and no `.env` file to fall back on."""
    monkeypatch.chdir(tmp_path)
    for name, value in GOOGLE_SETTINGS.items():
        monkeypatch.setenv(name, value)


@pytest.fixture
def no_google_env(monkeypatch, tmp_path):
    """No Google setting in the environment, and no `.env` file to fall back on."""
    monkeypatch.chdir(tmp_path)
    for name in GOOGLE_SETTINGS:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def unbuilt_provider(monkeypatch):
    """Forgets any `PROVIDER` the module already built, and the one the test builds."""
    monkeypatch.delitem(vars(google_module), "PROVIDER", raising=False)
    yield
    vars(google_module).pop("PROVIDER", None)


class TestAudience:
    @pytest.mark.parametrize(
        "client_id",
        [WEB_CLIENT_ID, IOS_CLIENT_ID, ANDROID_CLIENT_ID],
        ids=["web", "ios", "android"],
    )
    async def test_accepts_a_token_for_any_of_the_apps_clients(
        self, google, signing_key, client_id
    ):
        assertion = signing_key.sign(google_claims(aud=client_id))

        identity = await google.exchange_native(assertion=assertion, nonce=NONCE)

        assert identity.subject == SUBJECT

    @pytest.mark.parametrize(
        "aud",
        [
            pytest.param(OTHER_APP_CLIENT_ID, id="another-app"),
            pytest.param([WEB_CLIENT_ID, OTHER_APP_CLIENT_ID], id="shared-with-another-app"),
            pytest.param(ABSENT, id="absent"),
        ],
    )
    async def test_rejects_a_token_addressed_to_any_other_application(
        self, google, signing_key, aud
    ):
        assertion = signing_key.sign(google_claims(aud=aud))

        with pytest.raises(ProviderAssertionInvalid):
            await google.exchange_native(assertion=assertion, nonce=NONCE)


class TestIssuer:
    @pytest.mark.parametrize("iss", ["https://accounts.google.com", "accounts.google.com"])
    async def test_accepts_both_of_googles_issuers(self, google, signing_key, iss):
        assertion = signing_key.sign(google_claims(iss=iss))

        identity = await google.exchange_native(assertion=assertion, nonce=NONCE)

        assert identity.subject == SUBJECT

    @pytest.mark.parametrize(
        "iss",
        [
            pytest.param("https://appleid.apple.com", id="apple"),
            pytest.param("https://accounts.google.com.evil.example", id="lookalike"),
            pytest.param(ABSENT, id="absent"),
        ],
    )
    async def test_rejects_any_other_issuer(self, google, signing_key, iss):
        assertion = signing_key.sign(google_claims(iss=iss))

        with pytest.raises(ProviderAssertionInvalid):
            await google.exchange_native(assertion=assertion, nonce=NONCE)


class TestTamperedAssertions:
    async def test_rejects_a_token_signed_by_a_key_google_never_published(
        self, google, forged_signing_key
    ):
        assertion = forged_signing_key.sign(google_claims())

        with pytest.raises(ProviderAssertionInvalid):
            await google.exchange_native(assertion=assertion, nonce=NONCE)

    async def test_rejects_an_unsigned_token(self, google, signing_key):
        assertion = signing_key.sign_with_none(google_claims())

        with pytest.raises(ProviderAssertionInvalid):
            await google.exchange_native(assertion=assertion, nonce=NONCE)

    async def test_rejects_an_expired_token(self, google, signing_key):
        now = int(time.time())
        assertion = signing_key.sign(google_claims(iat=now - 3720, exp=now - 120))

        with pytest.raises(ProviderAssertionInvalid):
            await google.exchange_native(assertion=assertion, nonce=NONCE)

    async def test_rejects_a_token_minted_for_another_attempts_nonce(self, google, signing_key):
        assertion = signing_key.sign(google_claims(nonce="nonce-of-another-attempt"))

        with pytest.raises(ProviderAssertionInvalid):
            await google.exchange_native(assertion=assertion, nonce=NONCE)

    async def test_rejects_a_token_without_a_nonce(self, google, signing_key):
        assertion = signing_key.sign(google_claims(nonce=ABSENT))

        with pytest.raises(ProviderAssertionInvalid):
            await google.exchange_native(assertion=assertion, nonce=NONCE)

    @pytest.mark.parametrize(
        "sub", [pytest.param(ABSENT, id="absent"), pytest.param("", id="empty")]
    )
    async def test_rejects_a_token_without_a_subject(self, google, signing_key, sub):
        assertion = signing_key.sign(google_claims(sub=sub))

        with pytest.raises(ProviderAssertionInvalid):
            await google.exchange_native(assertion=assertion, nonce=NONCE)

    @pytest.mark.parametrize(
        "assertion",
        [
            pytest.param("", id="empty"),
            pytest.param("not-a-token", id="garbage"),
            pytest.param("e30.e30.", id="empty-segments"),
        ],
    )
    async def test_rejects_a_malformed_assertion(self, google, assertion):
        with pytest.raises(ProviderAssertionInvalid):
            await google.exchange_native(assertion=assertion, nonce=NONCE)


class TestClockSkew:
    async def test_accepts_a_token_that_expired_less_than_a_minute_ago(self, google, signing_key):
        now = int(time.time())

        identity = await sign_in(google, signing_key, iat=now - 3630, exp=now - 30)

        assert identity.subject == SUBJECT

    async def test_accepts_a_token_issued_moments_in_the_future(self, google, signing_key):
        now = int(time.time())

        identity = await sign_in(google, signing_key, iat=now + 30, exp=now + 3630)

        assert identity.subject == SUBJECT

    async def test_rejects_a_token_that_expired_more_than_a_minute_ago(self, google, signing_key):
        now = int(time.time())

        with pytest.raises(ProviderAssertionInvalid):
            await sign_in(google, signing_key, iat=now - 3690, exp=now - 90)


class TestSigningKeyCache:
    async def test_fetches_keys_once_across_sign_ins(self, google, signing_key, jwks_endpoint):
        for _ in range(3):
            await sign_in(google, signing_key)

        assert jwks_endpoint.fetch_count == 1

    async def test_picks_up_a_rotated_key_with_exactly_one_refresh(
        self, google, signing_key, rotated_signing_key, jwks_endpoint, fake_clock
    ):
        await sign_in(google, signing_key)
        jwks_endpoint.publish(signing_key, rotated_signing_key)
        fake_clock.advance(JWKS_REFRESH_COOLDOWN + timedelta(seconds=1))

        identity = await sign_in(google, rotated_signing_key)

        assert identity.subject == SUBJECT
        assert jwks_endpoint.fetch_count == 2

    async def test_rejects_a_key_still_unknown_after_one_refresh(
        self, google, signing_key, rotated_signing_key, jwks_endpoint, fake_clock
    ):
        await sign_in(google, signing_key)
        fake_clock.advance(JWKS_REFRESH_COOLDOWN + timedelta(seconds=1))

        with pytest.raises(ProviderAssertionInvalid):
            await sign_in(google, rotated_signing_key)

        assert jwks_endpoint.fetch_count == 2

    async def test_refreshes_at_most_once_for_a_burst_of_unknown_keys(
        self, google, signing_key, rotated_signing_key, jwks_endpoint, fake_clock
    ):
        await sign_in(google, signing_key)
        fake_clock.advance(JWKS_REFRESH_COOLDOWN + timedelta(seconds=1))

        for _ in range(3):
            with pytest.raises(ProviderAssertionInvalid):
                await sign_in(google, rotated_signing_key)

        assert jwks_endpoint.fetch_count == 2

    async def test_fetches_keys_again_once_the_cache_expires(
        self, google, signing_key, jwks_endpoint, fake_clock
    ):
        await sign_in(google, signing_key)
        fake_clock.advance(JWKS_CACHE_TTL + timedelta(seconds=1))

        await sign_in(google, signing_key)

        assert jwks_endpoint.fetch_count == 2

    @pytest.mark.parametrize(
        "answer",
        [_unreachable, _server_error, _not_json, _no_keys],
        ids=["unreachable", "server-error", "not-json", "no-keys"],
    )
    async def test_reports_keys_it_cannot_fetch_as_unavailable(
        self, google_config, fake_clock, signing_key, answer
    ):
        google = GoogleProvider(
            google_config, transport=httpx.MockTransport(answer), clock=fake_clock
        )

        with pytest.raises(ProviderUnavailable):
            await sign_in(google, signing_key)


class TestIdentity:
    async def test_maps_a_verified_google_account_to_an_identity(self, google, signing_key):
        identity = await sign_in(google, signing_key)

        assert identity == ProviderIdentity(
            provider="google",
            subject=SUBJECT,
            email="ada@example.com",
            email_verified=True,
            is_private_relay=False,
            display_name=None,
        )

    @pytest.mark.parametrize(
        "email_verified",
        [False, ABSENT, None, "true", "false", 1],
        ids=["false", "absent", "null", "string-true", "string-false", "one"],
    )
    async def test_reports_the_email_unverified_unless_google_sent_true(
        self, google, signing_key, email_verified
    ):
        identity = await sign_in(google, signing_key, email_verified=email_verified)

        assert identity.email_verified is False
        assert identity.email == "ada@example.com"

    async def test_reports_no_email_when_google_sent_none(self, google, signing_key):
        identity = await sign_in(google, signing_key, email=ABSENT)

        assert identity.email is None
        assert identity.email_verified is False

    async def test_keeps_no_name_even_when_google_sends_one(self, google, signing_key):
        identity = await sign_in(google, signing_key, name="Ada Lovelace", given_name="Ada")

        assert identity.display_name is None


class TestConfiguration:
    @pytest.mark.parametrize("missing", list(GOOGLE_SETTINGS))
    def test_a_missing_setting_fails_construction(self, monkeypatch, google_env, missing):
        monkeypatch.delenv(missing)

        with pytest.raises(ValidationError):
            GoogleConfig()

    @pytest.mark.parametrize("blank", list(GOOGLE_SETTINGS))
    def test_a_blank_setting_counts_as_missing(self, monkeypatch, google_env, blank):
        monkeypatch.setenv(blank, "")

        with pytest.raises(ValidationError):
            GoogleConfig()

    def test_the_client_secret_stays_out_of_the_configs_repr(self, google_config):
        assert CLIENT_SECRET not in repr(google_config)
        assert CLIENT_SECRET not in str(google_config)

    def test_load_provider_reports_google_not_configured_without_settings(
        self, no_google_env, unbuilt_provider
    ):
        with pytest.raises(ProviderNotConfigured):
            load_provider("google")

    def test_load_provider_builds_google_once_from_complete_settings(
        self, google_env, unbuilt_provider
    ):
        provider = load_provider("google")

        assert isinstance(provider, GoogleProvider)
        assert provider.name == "google"
        assert load_provider("google") is provider

    def test_construction_makes_no_network_call(self, google_config, fake_google, fake_clock):
        GoogleProvider(
            google_config, transport=httpx.MockTransport(fake_google.handle), clock=fake_clock
        )

        assert fake_google.jwks.fetch_count == 0
        assert fake_google.token_requests == []


class TestAuthorizationUrl:
    def test_starts_googles_code_flow_for_the_web_client(self, google):
        url = google.authorization_url(state="the-state", nonce=NONCE, redirect_uri=REDIRECT_URI)

        parts = urlsplit(url)
        assert f"{parts.scheme}://{parts.netloc}{parts.path}" == GOOGLE_AUTHORIZATION_URL
        assert (
            dict(parse_qsl(parts.query)).items()
            >= {
                "client_id": WEB_CLIENT_ID,
                "response_type": "code",
                "scope": "openid email",
                "redirect_uri": REDIRECT_URI,
                "state": "the-state",
                "nonce": NONCE,
            }.items()
        )

    def test_never_puts_the_client_secret_in_the_url(self, google):
        url = google.authorization_url(state="the-state", nonce=NONCE, redirect_uri=REDIRECT_URI)

        assert CLIENT_SECRET not in url


class TestExchangeRedirect:
    async def test_trades_the_code_for_a_verified_identity(self, google, fake_google, signing_key):
        fake_google.answer_token_request = _token_response(signing_key.sign(google_claims()))

        identity = await google.exchange_redirect(
            code="the-code", redirect_uri=REDIRECT_URI, nonce=NONCE
        )

        assert identity.subject == SUBJECT
        [request] = fake_google.token_requests
        assert (
            dict(parse_qsl(request.content.decode())).items()
            >= {
                "grant_type": "authorization_code",
                "code": "the-code",
                "redirect_uri": REDIRECT_URI,
                "client_id": WEB_CLIENT_ID,
                "client_secret": CLIENT_SECRET,
            }.items()
        )

    async def test_verifies_the_returned_token_like_a_native_one(
        self, google, fake_google, signing_key
    ):
        fake_google.answer_token_request = _token_response(
            signing_key.sign(google_claims(nonce="nonce-of-another-attempt"))
        )

        with pytest.raises(ProviderAssertionInvalid):
            await google.exchange_redirect(code="the-code", redirect_uri=REDIRECT_URI, nonce=NONCE)

    @pytest.mark.parametrize(
        "answer",
        [
            pytest.param(
                lambda request: httpx.Response(400, json={"error": "invalid_grant"}),
                id="code-refused",
            ),
            pytest.param(
                lambda request: httpx.Response(401, json={"error": "invalid_client"}),
                id="client-refused",
            ),
            pytest.param(
                lambda request: httpx.Response(200, json={"access_token": "unused"}),
                id="no-id-token",
            ),
            pytest.param(_not_json, id="not-json"),
        ],
    )
    async def test_a_refused_or_unusable_exchange_is_invalid(self, google, fake_google, answer):
        fake_google.answer_token_request = answer

        with pytest.raises(ProviderAssertionInvalid):
            await google.exchange_redirect(code="the-code", redirect_uri=REDIRECT_URI, nonce=NONCE)

    @pytest.mark.parametrize(
        "answer", [_unreachable, _server_error], ids=["unreachable", "server-error"]
    )
    async def test_an_unreachable_token_endpoint_is_unavailable(self, google, fake_google, answer):
        fake_google.answer_token_request = answer

        with pytest.raises(ProviderUnavailable):
            await google.exchange_redirect(code="the-code", redirect_uri=REDIRECT_URI, nonce=NONCE)


class TestNothingSecretEscapes:
    async def test_a_rejected_assertion_is_never_echoed(self, google, forged_signing_key, caplog):
        assertion = forged_signing_key.sign(google_claims())

        with caplog.at_level(logging.DEBUG), pytest.raises(ProviderAssertionInvalid) as refused:
            await google.exchange_native(assertion=assertion, nonce=NONCE)

        assert assertion not in exception_text(refused.value)
        assert assertion not in caplog.text

    async def test_a_refused_code_and_the_client_secret_are_never_echoed(
        self, google, fake_google, caplog
    ):
        fake_google.answer_token_request = lambda request: httpx.Response(
            400, json={"error": "invalid_grant"}
        )

        with caplog.at_level(logging.DEBUG), pytest.raises(ProviderAssertionInvalid) as refused:
            await google.exchange_redirect(
                code="the-code-value", redirect_uri=REDIRECT_URI, nonce=NONCE
            )

        for secret in ("the-code-value", CLIENT_SECRET):
            assert secret not in exception_text(refused.value)
            assert secret not in caplog.text
