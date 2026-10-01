import importlib
import json
import logging
import sys
import traceback
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, parse_qsl, urlsplit

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from jwt.algorithms import RSAAlgorithm
from pydantic import ValidationError

from backend.auth.oauth import providers
from backend.auth.oauth.contract import ProviderIdentity
from backend.auth.oauth.exceptions import (
    ProviderAssertionInvalid,
    ProviderNotConfigured,
    ProviderUnavailable,
)
from backend.auth.oauth.registry import load_provider

MODULE = "backend.auth.oauth.providers.apple"
APPLE = "https://appleid.apple.com"
KEYS_URL = f"{APPLE}/auth/keys"
TOKEN_URL = f"{APPLE}/auth/token"

TEAM_ID = "TEAM123456"
SERVICES_ID = "com.example.backendtemplate.web"
BUNDLE_ID = "com.example.backendtemplate"
KEY_ID = "KEY1234567"
SUBJECT = "001234.5a6b7c8d9e0f.1234"
EMAIL = "ada@example.com"
RELAY_EMAIL = "x7k2p9q4@privaterelay.appleid.com"
STATE = "state-from-start"
NONCE = "nonce-from-start"
REDIRECT_URI = "https://app.example.com/auth/oauth/apple/callback"

OMIT = object()

# The app's `.p8` key, which signs the client secret sent to Apple.
P8_KEY = ec.generate_private_key(ec.SECP256R1())
# Apple's own keys, which sign identity tokens and are published at /auth/keys.
APPLE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
ROTATED_APPLE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
STRANGER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)

APPLE_SETTINGS = {
    "APPLE_TEAM_ID": TEAM_ID,
    "APPLE_SERVICES_ID": SERVICES_ID,
    "APPLE_BUNDLE_ID": BUNDLE_ID,
    "APPLE_KEY_ID": KEY_ID,
    "APPLE_PRIVATE_KEY": P8_KEY.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode(),
}


def _from_now(seconds: int) -> int:
    return int(datetime.now(UTC).timestamp()) + seconds


def _jwk(kid: str, key: rsa.RSAPrivateKey) -> dict:
    jwk = RSAAlgorithm.to_jwk(key.public_key(), as_dict=True)
    return jwk | {"kid": kid, "use": "sig", "alg": "RS256"}


def _key_fragments() -> list[str]:
    """The base64 lines of the `.p8` key. Any one of them in an error or a log is a leak."""
    pem = APPLE_SETTINGS["APPLE_PRIVATE_KEY"]
    return [line for line in pem.splitlines() if "-----" not in line]


def _assert_never_shown(secrets: list[str], exc: BaseException, logs: str) -> None:
    """Fail if a secret is in `logs`, or in what a log line with `exc`'s traceback would print."""
    shown = "".join(traceback.format_exception(exc)) + logs
    assert [secret for secret in secrets if secret in shown] == []


def _client_secret_claims(client_secret: str) -> dict:
    return jwt.decode(
        client_secret,
        P8_KEY.public_key(),
        algorithms=["ES256"],
        audience=APPLE,
        options={"verify_exp": False, "verify_iat": False},
    )


class FakeClock:
    """The time the adapter reads. Moves only when a test moves it."""

    def __init__(self) -> None:
        self.now = datetime.now(UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, delta: timedelta) -> None:
        self.now += delta


class FakeApple:
    """Apple's sign-in endpoints, answered in-process through an httpx transport.

    Signs identity tokens with its own RSA key and publishes that key at
    `/auth/keys`, as Apple does. A code trades once. Records every request.
    Set `unreachable` or `server_error` to take Apple down.
    """

    def __init__(self) -> None:
        self.published: dict[str, rsa.RSAPrivateKey] = {"apple-key-1": APPLE_KEY}
        self.signing_kid = "apple-key-1"
        self.codes: dict[str, str] = {}
        self.codes_issued = 0
        self.requests: list[httpx.Request] = []
        self.token_forms: list[dict[str, str]] = []
        self.key_fetches = 0
        self.unreachable = False
        self.server_error = False
        self.transport = httpx.MockTransport(self._handle)

    def id_token(self, *, kid=None, signing_key=None, algorithm="RS256", **claims) -> str:
        """An identity token as Apple signs it. `claims` override defaults; `OMIT` drops one."""
        now = _from_now(0)
        payload = {
            "iss": APPLE,
            "aud": BUNDLE_ID,
            "iat": now,
            "exp": now + 600,
            "sub": SUBJECT,
            "nonce": NONCE,
            "nonce_supported": True,
            "email": EMAIL,
            "email_verified": True,
            "is_private_email": False,
            "auth_time": now,
        } | claims
        payload = {name: value for name, value in payload.items() if value is not OMIT}
        kid = kid or self.signing_kid
        if signing_key is None and algorithm != "none":
            signing_key = self.published[kid]
        return jwt.encode(payload, signing_key, algorithm=algorithm, headers={"kid": kid})

    def issue_code(self, id_token: str) -> str:
        """An authorization code Apple trades, once, for `id_token`."""
        self.codes_issued += 1
        code = f"apple-code-{self.codes_issued}"
        self.codes[code] = id_token
        return code

    def rotate_keys(self) -> None:
        """Publish a new key under a new `kid` and retire the old one, as Apple does."""
        self.published = {"apple-key-2": ROTATED_APPLE_KEY}
        self.signing_kid = "apple-key-2"

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        is_token_request = request.method == "POST" and request.url == TOKEN_URL
        if is_token_request:
            self.token_forms.append(dict(parse_qsl(request.content.decode())))
        if self.unreachable:
            raise httpx.ConnectError("appleid.apple.com is unreachable", request=request)
        if self.server_error:
            return httpx.Response(503)
        if request.method == "GET" and request.url == KEYS_URL:
            self.key_fetches += 1
            keys = [_jwk(kid, key) for kid, key in self.published.items()]
            return httpx.Response(200, json={"keys": keys})
        if is_token_request:
            id_token = self.codes.pop(self.token_forms[-1].get("code", ""), None)
            if id_token is None:
                return httpx.Response(400, json={"error": "invalid_grant"})
            return httpx.Response(
                200,
                json={
                    "access_token": "apple-access-token",
                    "token_type": "Bearer",
                    "expires_in": 3600,
                    "refresh_token": "apple-refresh-token",
                    "id_token": id_token,
                },
            )
        return httpx.Response(404)


def _forget_apple_module() -> None:
    sys.modules.pop(MODULE, None)
    vars(providers).pop("apple", None)


@pytest.fixture
def apple_env(monkeypatch, tmp_path):
    """A complete Apple configuration in the environment, and no `.env` file in reach.

    The adapter module builds its provider on import, from the environment, so
    it is dropped from the import system before and after each test.
    """
    for name, value in APPLE_SETTINGS.items():
        monkeypatch.setenv(name, value)
    monkeypatch.chdir(tmp_path)
    _forget_apple_module()
    yield
    _forget_apple_module()


@pytest.fixture
def apple(apple_env):
    """The `providers.apple` module, imported fresh."""
    return importlib.import_module(MODULE)


@pytest.fixture
def fake_apple() -> FakeApple:
    return FakeApple()


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def provider(apple, fake_apple, clock):
    """An `AppleProvider` that reaches `fake_apple` and reads `clock`."""
    config = apple.AppleConfig(**APPLE_SETTINGS, _env_file=None)
    return apple.AppleProvider(config, transport=fake_apple.transport, clock=clock)


async def _web_sign_in(provider, fake_apple, *, user_details=None, **token) -> ProviderIdentity:
    """Apple issues a code for a token addressed to the Services ID; the adapter trades it."""
    code = fake_apple.issue_code(fake_apple.id_token(**({"aud": SERVICES_ID} | token)))
    return await provider.exchange_redirect(
        code=code, redirect_uri=REDIRECT_URI, nonce=NONCE, user_details=user_details
    )


class TestAuthorizationUrl:
    def test_starts_a_form_post_sign_in_for_the_services_id(self, provider, fake_apple):
        url = urlsplit(
            provider.authorization_url(state=STATE, nonce=NONCE, redirect_uri=REDIRECT_URI)
        )

        assert (url.scheme, url.netloc, url.path) == (
            "https",
            "appleid.apple.com",
            "/auth/authorize",
        )
        assert parse_qs(url.query) == {
            "client_id": [SERVICES_ID],
            "redirect_uri": [REDIRECT_URI],
            "response_type": ["code"],
            "response_mode": ["form_post"],
            "scope": ["name email"],
            "state": [STATE],
            "nonce": [NONCE],
        }
        assert fake_apple.requests == []


class TestNativeSignIn:
    async def test_returns_the_identity_apple_asserts(self, provider, fake_apple):
        identity = await provider.exchange_native(assertion=fake_apple.id_token(), nonce=NONCE)

        assert identity == ProviderIdentity(
            provider="apple",
            subject=SUBJECT,
            email=EMAIL,
            email_verified=True,
            is_private_relay=False,
            display_name=None,
        )

    @pytest.mark.parametrize("audience", [BUNDLE_ID, SERVICES_ID])
    async def test_accepts_a_token_for_either_of_the_apps_identities(
        self, provider, fake_apple, audience
    ):
        token = fake_apple.id_token(aud=audience)

        identity = await provider.exchange_native(assertion=token, nonce=NONCE)

        assert identity.subject == SUBJECT

    @pytest.mark.parametrize(
        "audience", ["com.attacker.app", "com.example.backendtemplate.evil", "com.example"]
    )
    async def test_refuses_a_token_for_another_app(self, provider, fake_apple, audience):
        token = fake_apple.id_token(aud=audience)

        with pytest.raises(ProviderAssertionInvalid):
            await provider.exchange_native(assertion=token, nonce=NONCE)

    @pytest.mark.parametrize(
        "skew",
        [
            pytest.param(lambda: {"exp": _from_now(-30)}, id="expired-30s-ago"),
            pytest.param(lambda: {"iat": _from_now(30)}, id="issued-30s-ahead"),
        ],
    )
    async def test_allows_a_minute_of_clock_skew(self, provider, fake_apple, skew):
        token = fake_apple.id_token(**skew())

        identity = await provider.exchange_native(assertion=token, nonce=NONCE)

        assert identity.subject == SUBJECT

    @pytest.mark.parametrize(
        "forge",
        [
            pytest.param(
                lambda a: a.id_token(signing_key=STRANGER_KEY), id="signed-by-another-key"
            ),
            pytest.param(lambda a: a.id_token(exp=_from_now(-300)), id="expired"),
            pytest.param(lambda a: a.id_token(iat=_from_now(600)), id="issued-in-the-future"),
            pytest.param(
                lambda a: a.id_token(iss="https://appleid.apple.com.evil.example"),
                id="wrong-issuer",
            ),
            pytest.param(lambda a: a.id_token(nonce="another-attempts-nonce"), id="nonce-mismatch"),
            pytest.param(lambda a: a.id_token(nonce=OMIT), id="nonce-missing"),
            pytest.param(lambda a: a.id_token(sub=OMIT), id="no-subject"),
            pytest.param(lambda a: a.id_token(sub=""), id="empty-subject"),
            pytest.param(lambda a: a.id_token(signing_key=None, algorithm="none"), id="unsigned"),
            pytest.param(lambda a: "not-a-token", id="malformed"),
        ],
    )
    async def test_refuses_a_token_that_fails_a_check(self, provider, fake_apple, forge):
        assertion = forge(fake_apple)

        with pytest.raises(ProviderAssertionInvalid):
            await provider.exchange_native(assertion=assertion, nonce=NONCE)

    async def test_refuses_and_says_so_when_apple_could_not_carry_the_nonce(
        self, provider, fake_apple
    ):
        token = fake_apple.id_token(nonce=OMIT, nonce_supported=False)

        with pytest.raises(ProviderAssertionInvalid, match=r"(?i)nonce.*support"):
            await provider.exchange_native(assertion=token, nonce=NONCE)


class TestWebSignIn:
    async def test_trades_the_code_for_the_identity_in_apples_token(self, provider, fake_apple):
        identity = await _web_sign_in(provider, fake_apple)

        assert identity == ProviderIdentity(
            provider="apple",
            subject=SUBJECT,
            email=EMAIL,
            email_verified=True,
            is_private_relay=False,
            display_name=None,
        )

    async def test_sends_the_code_to_apple_as_the_services_id(self, provider, fake_apple):
        code = fake_apple.issue_code(fake_apple.id_token(aud=SERVICES_ID))

        await provider.exchange_redirect(code=code, redirect_uri=REDIRECT_URI, nonce=NONCE)

        form = fake_apple.token_forms[-1]
        assert form["grant_type"] == "authorization_code"
        assert form["code"] == code
        assert form["redirect_uri"] == REDIRECT_URI
        assert form["client_id"] == SERVICES_ID
        assert form["client_secret"]

    async def test_refuses_a_code_that_was_already_traded(self, provider, fake_apple):
        code = fake_apple.issue_code(fake_apple.id_token(aud=SERVICES_ID))
        await provider.exchange_redirect(code=code, redirect_uri=REDIRECT_URI, nonce=NONCE)

        with pytest.raises(ProviderAssertionInvalid):
            await provider.exchange_redirect(code=code, redirect_uri=REDIRECT_URI, nonce=NONCE)

    async def test_a_refused_code_is_not_retried(self, provider, fake_apple):
        code = "expired-or-never-issued"

        with pytest.raises(ProviderAssertionInvalid):
            await provider.exchange_redirect(code=code, redirect_uri=REDIRECT_URI, nonce=NONCE)
        assert len(fake_apple.token_forms) == 1

    @pytest.mark.parametrize(
        "token",
        [
            pytest.param({"nonce": "another-attempts-nonce"}, id="nonce-mismatch"),
            pytest.param({"aud": "com.attacker.app"}, id="another-app"),
            pytest.param({"signing_key": STRANGER_KEY}, id="signed-by-another-key"),
        ],
    )
    async def test_still_checks_the_token_apple_returns(self, provider, fake_apple, token):
        with pytest.raises(ProviderAssertionInvalid):
            await _web_sign_in(provider, fake_apple, **token)

    @pytest.mark.parametrize("outage", ["unreachable", "server_error"])
    async def test_apple_being_down_is_retryable(self, provider, fake_apple, outage):
        setattr(fake_apple, outage, True)

        with pytest.raises(ProviderUnavailable):
            await _web_sign_in(provider, fake_apple)


class TestClientSecret:
    async def test_is_a_short_lived_es256_jwt_from_the_team_for_the_services_id(
        self, provider, fake_apple, clock
    ):
        await _web_sign_in(provider, fake_apple)
        client_secret = fake_apple.token_forms[-1]["client_secret"]

        header = jwt.get_unverified_header(client_secret)
        claims = _client_secret_claims(client_secret)

        assert (header["alg"], header["kid"]) == ("ES256", KEY_ID)
        assert (claims["iss"], claims["sub"], claims["aud"]) == (TEAM_ID, SERVICES_ID, APPLE)
        assert claims["iat"] <= clock.now.timestamp() < claims["exp"]
        assert claims["exp"] - claims["iat"] <= timedelta(hours=1).total_seconds()

    async def test_is_reused_while_it_is_still_valid(self, provider, fake_apple, clock):
        await _web_sign_in(provider, fake_apple)
        clock.advance(timedelta(seconds=30))
        await _web_sign_in(provider, fake_apple)

        first, second = (form["client_secret"] for form in fake_apple.token_forms)
        assert first == second

    async def test_is_reminted_once_it_expires(self, provider, fake_apple, clock):
        await _web_sign_in(provider, fake_apple)
        first = fake_apple.token_forms[-1]["client_secret"]
        expiry = datetime.fromtimestamp(_client_secret_claims(first)["exp"], UTC)
        clock.now = expiry + timedelta(seconds=1)

        await _web_sign_in(provider, fake_apple)

        second = fake_apple.token_forms[-1]["client_secret"]
        assert second != first
        assert _client_secret_claims(second)["exp"] > clock.now.timestamp()


class TestClaims:
    @pytest.mark.parametrize(
        ("claim", "expected"),
        [
            (True, True),
            ("true", True),
            (False, False),
            ("false", False),
            pytest.param(OMIT, False, id="absent"),
        ],
    )
    async def test_reads_is_private_email_as_a_string_or_a_boolean(
        self, provider, fake_apple, claim, expected
    ):
        token = fake_apple.id_token(email=RELAY_EMAIL, is_private_email=claim)

        identity = await provider.exchange_native(assertion=token, nonce=NONCE)

        assert identity.is_private_relay is expected
        assert identity.email == RELAY_EMAIL

    @pytest.mark.parametrize(
        ("claim", "expected"),
        [
            (True, True),
            ("true", True),
            (False, False),
            ("false", False),
            pytest.param(OMIT, False, id="absent"),
            ("yes", False),
            (1, False),
        ],
    )
    async def test_counts_the_email_as_verified_only_when_apple_says_so(
        self, provider, fake_apple, claim, expected
    ):
        token = fake_apple.id_token(email_verified=claim)

        identity = await provider.exchange_native(assertion=token, nonce=NONCE)

        assert identity.email_verified is expected

    async def test_a_token_without_an_email_has_none(self, provider, fake_apple):
        token = fake_apple.id_token(email=OMIT, email_verified=OMIT)

        identity = await provider.exchange_native(assertion=token, nonce=NONCE)

        assert identity.email is None
        assert identity.email_verified is False


class TestDisplayName:
    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ({"firstName": "Ada", "lastName": "Lovelace"}, "Ada Lovelace"),
            ({"firstName": "Ada"}, "Ada"),
            ({"lastName": "Lovelace"}, "Lovelace"),
        ],
    )
    async def test_web_first_sign_in_takes_the_name_from_user_details(
        self, provider, fake_apple, name, expected
    ):
        user_details = json.dumps({"name": name, "email": EMAIL})

        identity = await _web_sign_in(provider, fake_apple, user_details=user_details)

        assert identity.display_name == expected

    async def test_web_later_sign_in_has_no_name(self, provider, fake_apple):
        identity = await _web_sign_in(provider, fake_apple)

        assert identity.display_name is None

    @pytest.mark.parametrize(
        "user_details", ["not json", "[]", '{"name": "Ada"}', '{"name": {"firstName": 42}}']
    )
    async def test_unreadable_user_details_are_ignored(self, provider, fake_apple, user_details):
        identity = await _web_sign_in(provider, fake_apple, user_details=user_details)

        assert identity.display_name is None
        assert identity.subject == SUBJECT

    async def test_user_details_never_change_the_email(self, provider, fake_apple):
        user_details = json.dumps({"name": {"firstName": "Ada"}, "email": "someone@example.com"})

        identity = await _web_sign_in(provider, fake_apple, user_details=user_details)

        assert identity.email == EMAIL

    async def test_native_first_sign_in_keeps_the_name_the_app_sent(self, provider, fake_apple):
        identity = await provider.exchange_native(
            assertion=fake_apple.id_token(), nonce=NONCE, display_name="Ada Lovelace"
        )

        assert identity.display_name == "Ada Lovelace"

    @pytest.mark.parametrize("display_name", [None, "", "   "])
    async def test_native_later_sign_in_has_no_name(self, provider, fake_apple, display_name):
        identity = await provider.exchange_native(
            assertion=fake_apple.id_token(), nonce=NONCE, display_name=display_name
        )

        assert identity.display_name is None


class TestAppleKeys:
    async def test_are_fetched_once_not_per_sign_in(self, provider, fake_apple):
        for _ in range(3):
            await provider.exchange_native(assertion=fake_apple.id_token(), nonce=NONCE)

        assert fake_apple.key_fetches == 1

    async def test_an_unknown_key_id_fetches_them_again_once(self, provider, fake_apple):
        await provider.exchange_native(assertion=fake_apple.id_token(), nonce=NONCE)
        fake_apple.rotate_keys()

        identity = await provider.exchange_native(assertion=fake_apple.id_token(), nonce=NONCE)

        assert identity.subject == SUBJECT
        assert fake_apple.key_fetches == 2

    async def test_a_key_apple_never_published_is_refused_after_one_refetch(
        self, provider, fake_apple
    ):
        await provider.exchange_native(assertion=fake_apple.id_token(), nonce=NONCE)
        forged = fake_apple.id_token(kid="never-published", signing_key=STRANGER_KEY)

        with pytest.raises(ProviderAssertionInvalid):
            await provider.exchange_native(assertion=forged, nonce=NONCE)
        assert fake_apple.key_fetches == 2

    async def test_are_fetched_again_once_a_day_old(self, provider, fake_apple, clock):
        await provider.exchange_native(assertion=fake_apple.id_token(), nonce=NONCE)
        clock.advance(timedelta(days=1))

        await provider.exchange_native(assertion=fake_apple.id_token(), nonce=NONCE)

        assert fake_apple.key_fetches == 2

    @pytest.mark.parametrize("outage", ["unreachable", "server_error"])
    async def test_apple_being_down_is_retryable(self, provider, fake_apple, outage):
        setattr(fake_apple, outage, True)

        with pytest.raises(ProviderUnavailable):
            await provider.exchange_native(assertion=fake_apple.id_token(), nonce=NONCE)


class TestSecretsStayOut:
    @pytest.mark.parametrize("outage", [None, "unreachable", "server_error"])
    async def test_a_failed_web_sign_in_shows_no_key_client_secret_or_code(
        self, provider, fake_apple, caplog, outage
    ):
        caplog.set_level(logging.DEBUG)
        if outage:
            setattr(fake_apple, outage, True)
        code = "code-apple-refuses"

        with pytest.raises((ProviderAssertionInvalid, ProviderUnavailable)) as exc_info:
            await provider.exchange_redirect(code=code, redirect_uri=REDIRECT_URI, nonce=NONCE)

        client_secret = fake_apple.token_forms[-1]["client_secret"]
        _assert_never_shown([*_key_fragments(), client_secret, code], exc_info.value, caplog.text)

    @pytest.mark.parametrize("outage", [None, "unreachable"])
    async def test_a_failed_native_sign_in_shows_no_assertion(
        self, provider, fake_apple, caplog, outage
    ):
        caplog.set_level(logging.DEBUG)
        if outage:
            setattr(fake_apple, outage, True)
        assertion = fake_apple.id_token(signing_key=STRANGER_KEY)

        with pytest.raises((ProviderAssertionInvalid, ProviderUnavailable)) as exc_info:
            await provider.exchange_native(assertion=assertion, nonce=NONCE)

        signature = assertion.rsplit(".", 1)[1]
        _assert_never_shown([assertion, signature], exc_info.value, caplog.text)

    def test_settings_never_show_the_private_key(self, apple):
        config = apple.AppleConfig(**APPLE_SETTINGS, _env_file=None)

        shown = repr(config) + str(config)

        assert [fragment for fragment in _key_fragments() if fragment in shown] == []

    def test_incomplete_settings_never_echo_the_private_key(self, apple, monkeypatch):
        monkeypatch.delenv("APPLE_TEAM_ID")

        with pytest.raises(ValidationError) as exc_info:
            apple.AppleConfig(_env_file=None)

        _assert_never_shown(_key_fragments(), exc_info.value, "")


class TestRegistration:
    def test_is_found_by_name_when_configured(self, apple_env):
        assert load_provider("apple").name == "apple"

    def test_is_not_configured_when_a_setting_is_missing(self, apple_env, monkeypatch):
        monkeypatch.delenv("APPLE_TEAM_ID")

        with pytest.raises(ProviderNotConfigured) as exc_info:
            load_provider("apple")

        _assert_never_shown(_key_fragments(), exc_info.value, "")

    def test_building_it_makes_no_request(self, provider, fake_apple):
        assert fake_apple.requests == []
