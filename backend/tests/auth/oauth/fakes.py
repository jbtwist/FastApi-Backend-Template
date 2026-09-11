import uuid
from datetime import datetime
from urllib.parse import urlencode

from sqlalchemy.exc import IntegrityError

from backend.auth.oauth.contract import ProviderIdentity
from backend.auth.oauth.exceptions import ProviderAssertionInvalid
from backend.auth.oauth.models import OAuthIdentity


class FakeOAuthProvider:
    """An `OAuthProvider` that returns one canned identity without any network access.

    Its assertions and authorization codes are `"<name>:<nonce>"` strings (see
    `assertion_for`), so the nonce echo check still runs: an assertion minted for
    one nonce is refused under another, as a real adapter refuses an ID token
    whose `nonce` claim differs.
    """

    name = "fake"

    def __init__(self, identity: ProviderIdentity | None = None) -> None:
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
        self, *, code: str, redirect_uri: str, nonce: str
    ) -> ProviderIdentity:
        return self._verify(code, nonce=nonce)

    async def exchange_native(self, *, assertion: str, nonce: str) -> ProviderIdentity:
        return self._verify(assertion, nonce=nonce)

    def _verify(self, assertion: str, *, nonce: str) -> ProviderIdentity:
        if assertion != self.assertion_for(nonce):
            raise ProviderAssertionInvalid(self.name)
        return self.identity


class SecondFakeOAuthProvider(FakeOAuthProvider):
    """A second provider under its own name, proving a new one needs no shared edit."""

    name = "second_fake"


class FakeOAuthIdentityRepository:
    """Mirrors `oauth_identity_provider_subject_key`: a duplicate link raises `IntegrityError`."""

    def __init__(self) -> None:
        self._identities_by_id: dict[uuid.UUID, OAuthIdentity] = {}

    async def get_by_provider_subject(
        self, provider: str, provider_subject: str
    ) -> OAuthIdentity | None:
        for identity in self._identities_by_id.values():
            if identity.provider == provider and identity.provider_subject == provider_subject:
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
