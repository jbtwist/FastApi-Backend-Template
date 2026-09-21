"""Google sign-in.

Web, iOS and Android each have their own Google client ID, and a token addressed
to any of them is accepted. The web flow trades an authorization code for an ID
token; the native flow submits the one the platform SDK returned. Both are
verified the same way.
"""

import time
from collections.abc import Callable
from datetime import timedelta
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt
from jwt import PyJWK, PyJWKSet
from jwt.exceptions import PyJWTError
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from backend.auth.oauth.contract import ProviderIdentity
from backend.auth.oauth.exceptions import ProviderAssertionInvalid, ProviderUnavailable

PROVIDER_NAME = "google"

GOOGLE_AUTHORIZATION_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_ISSUERS = frozenset({"https://accounts.google.com", "accounts.google.com"})
GOOGLE_SCOPE = "openid email"

CLOCK_SKEW_LEEWAY = timedelta(seconds=60)
JWKS_CACHE_TTL = timedelta(hours=1)
JWKS_REFRESH_COOLDOWN = timedelta(seconds=30)
REQUEST_TIMEOUT = httpx.Timeout(5.0)


class GoogleConfig(BaseSettings):
    """Google sign-in settings, read from the flat `.env` namespace.

    A missing or blank field fails construction, which `load_provider` reports as
    Google not being configured.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    GOOGLE_CLIENT_ID_WEB: str = Field(min_length=1)
    GOOGLE_CLIENT_ID_IOS: str = Field(min_length=1)
    GOOGLE_CLIENT_ID_ANDROID: str = Field(min_length=1)
    GOOGLE_CLIENT_SECRET: SecretStr = Field(min_length=1)


def _key_id(assertion: str) -> str:
    """Read the `kid` from an assertion's header, before anything in it is trusted."""
    try:
        header = jwt.get_unverified_header(assertion)
    except PyJWTError as exc:
        raise ProviderAssertionInvalid(PROVIDER_NAME) from exc
    kid = header.get("kid")
    if not isinstance(kid, str) or not kid:
        raise ProviderAssertionInvalid(PROVIDER_NAME)
    return kid


def _find(keys: PyJWKSet, kid: str) -> PyJWK | None:
    return next((key for key in keys.keys if key.key_id == kid), None)


def _audiences_of(claims: dict[str, Any]) -> set[str]:
    aud = claims["aud"]
    return {aud} if isinstance(aud, str) else set(aud)


class _SigningKeys:
    """Google's published signing keys, cached in this process.

    Refetches past `JWKS_CACHE_TTL`, and when a token names an unknown key. The
    second kind is rate-limited to once per `JWKS_REFRESH_COOLDOWN`, so made-up
    key IDs can't make every sign-in refetch.
    """

    def __init__(
        self, *, transport: httpx.AsyncBaseTransport | None, clock: Callable[[], float]
    ) -> None:
        self._transport = transport
        self._clock = clock
        self._keys: PyJWKSet | None = None
        self._fetched_at = 0.0

    async def get(self, kid: str) -> PyJWK:
        """Return the published key with this ID.

        Raises:
            ProviderAssertionInvalid: Google publishes no such key.
            ProviderUnavailable: the keys could not be fetched.
        """
        keys = self._keys
        if keys is None or self._age() >= JWKS_CACHE_TTL.total_seconds():
            keys = await self._fetch()
        key = _find(keys, kid)
        if key is None and self._age() >= JWKS_REFRESH_COOLDOWN.total_seconds():
            key = _find(await self._fetch(), kid)
        if key is None:
            raise ProviderAssertionInvalid(PROVIDER_NAME)
        return key

    def _age(self) -> float:
        return self._clock() - self._fetched_at

    async def _fetch(self) -> PyJWKSet:
        try:
            async with httpx.AsyncClient(
                transport=self._transport, timeout=REQUEST_TIMEOUT
            ) as client:
                response = await client.get(GOOGLE_JWKS_URL)
                response.raise_for_status()
                keys = PyJWKSet.from_dict(response.json())
        except (httpx.HTTPError, ValueError, PyJWTError) as exc:
            raise ProviderUnavailable(PROVIDER_NAME) from exc
        self._keys = keys
        self._fetched_at = self._clock()
        return keys


class GoogleProvider:
    """The Google `OAuthProvider`.

    Accepts an ID token only if Google signed it with a key it currently
    publishes, it comes from either Google issuer, every `aud` is one of the
    three client IDs, it is unexpired give or take `CLOCK_SKEW_LEEWAY`, and it
    carries the attempt's `nonce`.

    Google has no relay addresses and no name is requested, so `is_private_relay`
    is always false and `display_name` always `None`.
    """

    name = PROVIDER_NAME

    def __init__(
        self,
        config: GoogleConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Keep the settings; makes no network call.

        Args:
            config: the client IDs and secret.
            transport: where HTTP requests go; Google itself when `None`.
            clock: monotonic seconds, used to age the key cache.
        """
        self._config = config
        self._audiences = frozenset(
            {
                config.GOOGLE_CLIENT_ID_WEB,
                config.GOOGLE_CLIENT_ID_IOS,
                config.GOOGLE_CLIENT_ID_ANDROID,
            }
        )
        self._transport = transport
        self._signing_keys = _SigningKeys(transport=transport, clock=clock)

    def authorization_url(self, *, state: str, nonce: str, redirect_uri: str) -> str:
        """Build the URL that starts Google's code flow for the web client."""
        query = urlencode(
            {
                "client_id": self._config.GOOGLE_CLIENT_ID_WEB,
                "response_type": "code",
                "scope": GOOGLE_SCOPE,
                "redirect_uri": redirect_uri,
                "state": state,
                "nonce": nonce,
            }
        )
        return f"{GOOGLE_AUTHORIZATION_URL}?{query}"

    async def exchange_redirect(
        self, *, code: str, redirect_uri: str, nonce: str, user_details: str | None = None
    ) -> ProviderIdentity:
        """Trade an authorization code for an ID token at Google's token endpoint, then verify it.

        `user_details` is ignored: Google puts everything it vouches for in the
        ID token.

        Raises:
            ProviderAssertionInvalid: Google refused the code or sent no usable ID
                token, or the ID token failed verification.
            ProviderUnavailable: Google or its signing keys could not be reached.
        """
        assertion = await self._trade_code(code, redirect_uri=redirect_uri)
        return await self._identity(assertion, nonce=nonce)

    async def exchange_native(
        self, *, assertion: str, nonce: str, display_name: str | None = None
    ) -> ProviderIdentity:
        """Verify an ID token the platform SDK returned.

        `display_name` is ignored, for the same reason as in `exchange_redirect`.

        Raises:
            ProviderAssertionInvalid: the ID token failed verification.
            ProviderUnavailable: Google's signing keys could not be fetched.
        """
        return await self._identity(assertion, nonce=nonce)

    async def _trade_code(self, code: str, *, redirect_uri: str) -> str:
        """Trade an authorization code for the ID token Google returns with it."""
        form = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": self._config.GOOGLE_CLIENT_ID_WEB,
            "client_secret": self._config.GOOGLE_CLIENT_SECRET.get_secret_value(),
        }
        try:
            async with httpx.AsyncClient(
                transport=self._transport, timeout=REQUEST_TIMEOUT
            ) as client:
                response = await client.post(GOOGLE_TOKEN_URL, data=form)
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(PROVIDER_NAME) from exc
        if response.is_server_error:
            raise ProviderUnavailable(PROVIDER_NAME)
        if response.is_error:
            raise ProviderAssertionInvalid(PROVIDER_NAME)
        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderAssertionInvalid(PROVIDER_NAME) from exc
        assertion = payload.get("id_token") if isinstance(payload, dict) else None
        if not isinstance(assertion, str) or not assertion:
            raise ProviderAssertionInvalid(PROVIDER_NAME)
        return assertion

    async def _identity(self, assertion: str, *, nonce: str) -> ProviderIdentity:
        """Verify an ID token and normalise what it says about the person."""
        claims = await self._verified_claims(assertion, nonce=nonce)
        subject = claims["sub"]
        if not isinstance(subject, str) or not subject:
            raise ProviderAssertionInvalid(PROVIDER_NAME)
        email = claims.get("email")
        email = email if isinstance(email, str) and email else None
        return ProviderIdentity(
            provider=PROVIDER_NAME,
            subject=subject,
            email=email,
            email_verified=email is not None and claims.get("email_verified") is True,
            is_private_relay=False,
            display_name=None,
        )

    async def _verified_claims(self, assertion: str, *, nonce: str) -> dict[str, Any]:
        """Check the signature, issuer, audience, expiry and nonce, and return the claims."""
        key = await self._signing_keys.get(_key_id(assertion))
        try:
            claims = jwt.decode(
                assertion,
                key,
                algorithms=["RS256"],
                audience=list(self._audiences),
                issuer=GOOGLE_ISSUERS,
                leeway=CLOCK_SKEW_LEEWAY,
                options={"require": ["iss", "aud", "exp", "iat", "sub", "nonce"]},
            )
        except PyJWTError as exc:
            raise ProviderAssertionInvalid(PROVIDER_NAME) from exc
        if not self._audiences.issuperset(_audiences_of(claims)):
            raise ProviderAssertionInvalid(PROVIDER_NAME)
        if claims["nonce"] != nonce:
            raise ProviderAssertionInvalid(PROVIDER_NAME)
        return claims


def __getattr__(name: str) -> GoogleProvider:
    """Build `PROVIDER` from the environment the first time it is read.

    Lazy so the module imports without Google settings; `load_provider` still
    gets the settings error.
    """
    if name != "PROVIDER":
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    provider = GoogleProvider(GoogleConfig())
    globals()["PROVIDER"] = provider
    return provider
