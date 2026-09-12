"""Sign in with Apple: the adapter for the `apple` provider.

Ships switched off: leave `apple` out of `OAUTH_ENABLED_PROVIDERS`. Turning it on
needs an Apple Developer Program membership, which is what issues the Services ID,
the App ID and the `.p8` key. This code has never run against Apple's own
endpoints, so treat the real round trip as unverified.
"""

import hmac
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt
from jwt.exceptions import InvalidKeyError, InvalidTokenError, PyJWKError, PyJWKSetError
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from backend.auth.oauth.contract import ProviderIdentity
from backend.auth.oauth.exceptions import ProviderAssertionInvalid, ProviderUnavailable

APPLE = "https://appleid.apple.com"
AUTHORIZE_URL = f"{APPLE}/auth/authorize"
TOKEN_URL = f"{APPLE}/auth/token"
KEYS_URL = f"{APPLE}/auth/keys"

CLIENT_SECRET_LIFETIME = timedelta(minutes=10)
CLIENT_SECRET_REMINT_MARGIN = timedelta(seconds=30)
KEYS_CACHE_LIFETIME = timedelta(hours=12)
CLOCK_SKEW_LEEWAY = timedelta(seconds=60)
REQUEST_TIMEOUT = httpx.Timeout(5.0)


class AppleConfig(BaseSettings):
    """Apple sign-in settings, read from the flat `.env` namespace.

    - `APPLE_TEAM_ID`: the developer team. Issuer of the client secret.
    - `APPLE_SERVICES_ID`: the web client. Audience of web sign-ins.
    - `APPLE_BUNDLE_ID`: the iOS app. Audience of native sign-ins.
    - `APPLE_KEY_ID`, `APPLE_PRIVATE_KEY`: the `.p8` key that signs the client secret.

    A settings error never shows the values it read, so a half-filled `.env`
    cannot leak the key.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    APPLE_TEAM_ID: str
    APPLE_SERVICES_ID: str
    APPLE_BUNDLE_ID: str
    APPLE_KEY_ID: str
    APPLE_PRIVATE_KEY: SecretStr


def _asserted_true(value: object) -> bool:
    """Whether Apple positively said yes. Apple sends `true` or `"true"`; anything else is no."""
    return value is True or (isinstance(value, str) and value == "true")


def _trimmed(value: str | None) -> str | None:
    return value.strip() or None if isinstance(value, str) else None


def _name_from_user_details(user_details: str | None) -> str | None:
    """The person's name out of Apple's `user` field.

    The field is unsigned, sent once, and shaped
    `{"name": {"firstName": ..., "lastName": ...}}`. Anything unreadable is no name:
    a sign-in never fails over it.
    """
    if not user_details:
        return None
    try:
        details = json.loads(user_details)
    except ValueError:
        return None
    name = details.get("name") if isinstance(details, dict) else None
    if not isinstance(name, dict):
        return None
    parts = (_trimmed(name.get("firstName")), _trimmed(name.get("lastName")))
    return " ".join(part for part in parts if part) or None


class AppleProvider:
    """Sign in with Apple, on the native route and the web route.

    Every Apple token is checked before anything in it is used:

    - the signature, against Apple's published keys;
    - `iss` is Apple;
    - `aud` is the Services ID or the bundle ID;
    - `exp` and `iat`, allowing 60 seconds of clock skew;
    - `nonce` equals the one the sign-in started with.

    Apple's quirks, all handled here:

    - The client secret is an ES256 JWT signed with the `.p8` key. It is
      short-lived and reminted when it expires.
    - The web result comes back as a form POST.
    - The person's name comes once, on the first sign-in only.
    - `email_verified` and `is_private_email` may be strings or booleans.

    Building one makes no request. Apple's keys are fetched on first use, then cached.
    """

    name = "apple"

    def __init__(
        self,
        config: AppleConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        """Keep the settings. Makes no request.

        Args:
            config: Apple's identifiers and the `.p8` key.
            transport: how requests reach Apple. `None` means the network.
            clock: the current time, for the client secret and the key cache.
                `None` means the system clock. Token expiry is always checked
                against the system clock.
        """
        self._config = config
        self._transport = transport
        self._clock = clock
        self._client_secret: str | None = None
        self._client_secret_expires_at = datetime.min.replace(tzinfo=UTC)
        self._keys: dict[str, jwt.PyJWK] = {}
        self._keys_fetched_at: datetime | None = None

    def authorization_url(self, *, state: str, nonce: str, redirect_uri: str) -> str:
        """Build Apple's authorize URL for a web sign-in.

        Asks for `name email`, with `response_mode=form_post` so Apple posts the
        result back to `redirect_uri`.
        """
        query = urlencode(
            {
                "client_id": self._config.APPLE_SERVICES_ID,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "response_mode": "form_post",
                "scope": "name email",
                "state": state,
                "nonce": nonce,
            }
        )
        return f"{AUTHORIZE_URL}?{query}"

    async def exchange_redirect(
        self, *, code: str, redirect_uri: str, nonce: str, user_details: str | None = None
    ) -> ProviderIdentity:
        """Trade a web sign-in's code with Apple, then check the token Apple returns.

        A code works once, for five minutes, so a refused code is never retried.

        Args:
            user_details: Apple's `user` form field, sent on the first sign-in only.
                Only the name is read from it. Anything unreadable is ignored.

        Raises:
            ProviderAssertionInvalid: Apple refused the code, or its token failed a check.
            ProviderUnavailable: Apple could not be reached.
        """
        identity_token = await self._trade_code(code=code, redirect_uri=redirect_uri)
        claims = await self._checked_claims(identity_token, nonce=nonce)
        return self._identity(claims, display_name=_name_from_user_details(user_details))

    async def exchange_native(
        self, *, assertion: str, nonce: str, display_name: str | None = None
    ) -> ProviderIdentity:
        """Check an identity token the iOS app got from Apple.

        The token is the whole proof: there is no code to trade.

        Args:
            display_name: the name the app got from Apple on the first sign-in.
                Unsigned. Blank counts as none.

        Raises:
            ProviderAssertionInvalid: the token failed a check.
            ProviderUnavailable: Apple's keys could not be fetched.
        """
        claims = await self._checked_claims(assertion, nonce=nonce)
        return self._identity(claims, display_name=_trimmed(display_name))

    def _now(self) -> datetime:
        return self._clock() if self._clock is not None else datetime.now(UTC)

    def _identity(self, claims: dict[str, Any], *, display_name: str | None) -> ProviderIdentity:
        email = claims.get("email")
        return ProviderIdentity(
            provider=self.name,
            subject=claims["sub"],
            email=email if isinstance(email, str) and email else None,
            email_verified=_asserted_true(claims.get("email_verified")),
            is_private_relay=_asserted_true(claims.get("is_private_email")),
            display_name=display_name,
        )

    async def _trade_code(self, *, code: str, redirect_uri: str) -> str:
        form = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": self._config.APPLE_SERVICES_ID,
            "client_secret": self._current_client_secret(),
        }
        async with httpx.AsyncClient(transport=self._transport, timeout=REQUEST_TIMEOUT) as client:
            try:
                response = await client.post(TOKEN_URL, data=form)
            except httpx.HTTPError as exc:
                raise ProviderUnavailable("apple: the token endpoint could not be reached") from exc
        if response.status_code >= 500:
            raise ProviderUnavailable(f"apple: the token endpoint returned {response.status_code}")
        if response.status_code != httpx.codes.OK:
            raise ProviderAssertionInvalid("apple: the authorization code was refused")
        try:
            identity_token = response.json()["id_token"]
        except (ValueError, KeyError, TypeError) as exc:
            raise ProviderAssertionInvalid("apple: the token response carried no token") from exc
        return identity_token

    def _current_client_secret(self) -> str:
        """The client secret Apple wants in place of a static one, reminted once it ages out."""
        now = self._now()
        ages_out = now + CLIENT_SECRET_REMINT_MARGIN >= self._client_secret_expires_at
        if self._client_secret is None or ages_out:
            expires_at = now + CLIENT_SECRET_LIFETIME
            self._client_secret = self._mint_client_secret(now, expires_at)
            self._client_secret_expires_at = expires_at
        return self._client_secret

    def _mint_client_secret(self, now: datetime, expires_at: datetime) -> str:
        claims = {
            "iss": self._config.APPLE_TEAM_ID,
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
            "aud": APPLE,
            "sub": self._config.APPLE_SERVICES_ID,
        }
        try:
            return jwt.encode(
                claims,
                self._config.APPLE_PRIVATE_KEY.get_secret_value(),
                algorithm="ES256",
                headers={"kid": self._config.APPLE_KEY_ID},
            )
        except (InvalidKeyError, ValueError, TypeError) as exc:
            raise ProviderUnavailable("apple: the client secret could not be signed") from exc

    async def _checked_claims(self, identity_token: str, *, nonce: str) -> dict[str, Any]:
        try:
            key_id = jwt.get_unverified_header(identity_token).get("kid")
        except InvalidTokenError as exc:
            raise ProviderAssertionInvalid("apple: the identity token is malformed") from exc
        if not isinstance(key_id, str) or not key_id:
            raise ProviderAssertionInvalid("apple: the identity token names no signing key")

        signing_key = await self._signing_key(key_id)
        try:
            claims = jwt.decode(
                identity_token,
                signing_key.key,
                algorithms=["RS256"],
                audience=[self._config.APPLE_BUNDLE_ID, self._config.APPLE_SERVICES_ID],
                issuer=APPLE,
                leeway=CLOCK_SKEW_LEEWAY,
                options={"require": ["iss", "aud", "exp", "iat", "sub"]},
            )
        except InvalidTokenError as exc:
            raise ProviderAssertionInvalid("apple: the identity token failed verification") from exc

        self._check_nonce(claims, nonce=nonce)
        if not claims.get("sub"):
            raise ProviderAssertionInvalid("apple: the identity token carries no subject")
        return claims

    @staticmethod
    def _check_nonce(claims: dict[str, Any], *, nonce: str) -> None:
        echoed = claims.get("nonce")
        if echoed is None:
            if claims.get("nonce_supported") is False:
                raise ProviderAssertionInvalid(
                    "apple: this platform reports nonce is not supported, "
                    "so the sign-in cannot be bound to one"
                )
            raise ProviderAssertionInvalid("apple: the identity token echoed no nonce")
        if not isinstance(echoed, str) or not hmac.compare_digest(echoed, nonce):
            raise ProviderAssertionInvalid("apple: the identity token echoed a different nonce")

    async def _signing_key(self, key_id: str) -> jwt.PyJWK:
        """Apple's key with this `kid`. Fetches once if the cache cannot serve it."""
        if self._keys_are_stale() or key_id not in self._keys:
            await self._fetch_keys()
        key = self._keys.get(key_id)
        if key is None:
            raise ProviderAssertionInvalid("apple: the identity token names an unpublished key")
        return key

    def _keys_are_stale(self) -> bool:
        if self._keys_fetched_at is None:
            return True
        return self._now() - self._keys_fetched_at >= KEYS_CACHE_LIFETIME

    async def _fetch_keys(self) -> None:
        async with httpx.AsyncClient(transport=self._transport, timeout=REQUEST_TIMEOUT) as client:
            try:
                response = await client.get(KEYS_URL)
                response.raise_for_status()
                published = response.json()
            except httpx.HTTPError as exc:
                raise ProviderUnavailable("apple: the signing keys could not be fetched") from exc
            except ValueError as exc:
                raise ProviderUnavailable("apple: the signing keys were unreadable") from exc
        try:
            key_set = jwt.PyJWKSet.from_dict(published)
        except (PyJWKError, PyJWKSetError, AttributeError, KeyError, TypeError) as exc:
            raise ProviderUnavailable("apple: the signing keys were unreadable") from exc
        self._keys = {key.key_id: key for key in key_set.keys if key.key_id}
        self._keys_fetched_at = self._now()


PROVIDER = AppleProvider(AppleConfig())
