import uuid
from datetime import datetime, timedelta
from urllib.parse import urlencode

from sqlalchemy.exc import IntegrityError

from backend.auth.oauth.contract import ProviderIdentity
from backend.auth.oauth.exceptions import ProviderAssertionInvalid
from backend.auth.oauth.models import OAuthIdentity, OAuthLinkToken
from backend.auth.oauth.state import SignInAttempt
from tests.auth.fakes import _FakeSingleUseTokenRepository


class FakeOAuthProvider:
    """An `OAuthProvider` that returns one canned identity without any network access.

    Its assertions and authorization codes are `"<name>:<nonce>"` strings (see
    `assertion_for`), so the nonce echo check still runs: an assertion minted for
    one nonce is refused under another, as a real adapter refuses an ID token
    whose `nonce` claim differs.
    """

    name = "fake"

    def __init__(self, identity: ProviderIdentity | None = None) -> None:
        self.user_details: str | None = None
        self.identity = identity or ProviderIdentity(
            provider=self.name,
            subject=f"{self.name}-subject-1",
            email="ada@example.com",
            email_verified=True,
            is_private_relay=False,
            display_name=None,
        )

    def assertion_for(self, nonce: str) -> str:
        return f"{self.name}:{nonce}"

    def authorization_url(self, *, state: str, nonce: str, redirect_uri: str) -> str:
        query = urlencode({"state": state, "nonce": nonce, "redirect_uri": redirect_uri})
        return f"https://{self.name}.example/authorize?{query}"

    async def exchange_redirect(
        self, *, code: str, redirect_uri: str, nonce: str, user_details: str | None = None
    ) -> ProviderIdentity:
        self.user_details = user_details
        return self._verify(code, nonce=nonce)

    async def exchange_native(
        self, *, assertion: str, nonce: str, display_name: str | None = None
    ) -> ProviderIdentity:
        return self._verify(assertion, nonce=nonce)

    def _verify(self, assertion: str, *, nonce: str) -> ProviderIdentity:
        if assertion != self.assertion_for(nonce):
            raise ProviderAssertionInvalid(self.name)
        return self.identity


class SecondFakeOAuthProvider(FakeOAuthProvider):
    """A second provider under its own name, proving a new one needs no shared edit."""

    name = "second_fake"


class FakeOAuthIdentityRepository:
    """Mirrors both unique constraints: a duplicate `(provider, provider_subject)`, or a
    second identity for one `user_id`, raises `IntegrityError`."""

    def __init__(self) -> None:
        self._identities_by_id: dict[uuid.UUID, OAuthIdentity] = {}

    async def get_by_provider_subject(
        self, provider: str, provider_subject: str
    ) -> OAuthIdentity | None:
        for identity in self._identities_by_id.values():
            if identity.provider == provider and identity.provider_subject == provider_subject:
                return identity
        return None

    async def get_by_user_id(self, user_id: uuid.UUID) -> OAuthIdentity | None:
        for identity in self._identities_by_id.values():
            if identity.user_id == user_id:
                return identity
        return None

    async def create(
        self,
        *,
        user_id: uuid.UUID,
        provider: str,
        provider_subject: str,
        email_at_link: str | None,
        is_private_relay: bool,
        display_name: str | None,
    ) -> OAuthIdentity:
        if await self.get_by_provider_subject(provider, provider_subject) is not None:
            raise IntegrityError(
                "INSERT INTO oauth_identity",
                {},
                Exception("duplicate key: oauth_identity_provider_subject_key"),
            )
        if await self.get_by_user_id(user_id) is not None:
            raise IntegrityError(
                "INSERT INTO oauth_identity",
                {},
                Exception("duplicate key: oauth_identity_user_id_key"),
            )
        identity = OAuthIdentity(
            id=uuid.uuid4(),
            user_id=user_id,
            provider=provider,
            provider_subject=provider_subject,
            email_at_link=email_at_link,
            is_private_relay=is_private_relay,
            display_name=display_name,
            last_authenticated_at=None,
        )
        self._identities_by_id[identity.id] = identity
        return identity

    async def mark_authenticated(
        self, identity_id: uuid.UUID, *, authenticated_at: datetime
    ) -> None:
        self._identities_by_id[identity_id].last_authenticated_at = authenticated_at


class FakeOAuthLinkTokenRepository(_FakeSingleUseTokenRepository[OAuthLinkToken]):
    model = OAuthLinkToken

    async def create(
        self,
        *,
        user_id: uuid.UUID,
        token_hash: str,
        expires_at: datetime,
        identity: ProviderIdentity,
    ) -> OAuthLinkToken:
        token = OAuthLinkToken(
            id=uuid.uuid4(),
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            used_at=None,
            provider=identity.provider,
            provider_subject=identity.subject,
            email_at_link=identity.email,
            is_private_relay=identity.is_private_relay,
            display_name=identity.display_name,
        )
        self._tokens_by_id[token.id] = token
        return token

    async def invalidate_all_for_user(
        self, user_id: uuid.UUID, *, invalidated_at: datetime
    ) -> None:
        for token in self._tokens_by_id.values():
            if token.user_id == user_id and token.used_at is None:
                token.used_at = invalidated_at

    def all(self) -> list[OAuthLinkToken]:
        return list(self._tokens_by_id.values())


class FakeSignInStateStore:
    """An in-memory `SignInStateStore`; expiry is modelled by `expire`, not by a clock."""

    def __init__(self) -> None:
        self.attempts: dict[str, SignInAttempt] = {}
        self.ttls: dict[str, timedelta] = {}

    async def save(self, state: str, attempt: SignInAttempt, *, ttl: timedelta) -> None:
        self.attempts[state] = attempt
        self.ttls[state] = ttl

    async def consume(self, state: str) -> SignInAttempt | None:
        return self.attempts.pop(state, None)

    def expire(self, state: str) -> None:
        self.attempts.pop(state, None)
