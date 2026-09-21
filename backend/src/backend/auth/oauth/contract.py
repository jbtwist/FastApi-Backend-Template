"""The provider seam: what every sign-in provider adapter implements.

An adapter must:

- verify before trusting any of it: signature against current JWKS, `iss`, `aud`
  (a set, since providers ship several client identities), `exp` with 60 s
  leeway, and the echoed `nonce`
- cache its JWKS
- raise rather than return on failure
- keep raw assertions, codes, secrets and keys out of exceptions and logs
- construct without I/O, so a misconfigured provider can't stop the app booting
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ProviderIdentity:
    """What one verified provider assertion says about a person.

    Every field is provider-supplied and none of it is rendered to a user.
    `subject` is what finds a returning person; a verified `email` only ever
    finds an account to create or offer a link to, never one to sign in to.
    """

    provider: str
    subject: str
    email: str | None
    email_verified: bool
    is_private_relay: bool
    display_name: str | None


class OAuthProvider(Protocol):
    """One third-party sign-in provider.

    Everything that differs between providers lives behind these three methods;
    shared code knows only them and `ProviderIdentity`.
    """

    name: str

    def authorization_url(self, *, state: str, nonce: str, redirect_uri: str) -> str:
        """Build the URL that starts a redirect-route sign-in."""

    async def exchange_redirect(
        self, *, code: str, redirect_uri: str, nonce: str, user_details: str | None = None
    ) -> ProviderIdentity:
        """Trade an authorization code for a verified identity.

        Args:
            user_details: unsigned details some providers post back with the code
                on the first sign-in. A provider may read a `display_name` from
                it, and nothing else.

        Raises:
            ProviderAssertionInvalid: verification failed for any reason.
            ProviderUnavailable: the provider could not be reached.
        """

    async def exchange_native(
        self, *, assertion: str, nonce: str, display_name: str | None = None
    ) -> ProviderIdentity:
        """Verify an assertion the platform SDK produced on the device.

        Args:
            display_name: the name the device sent with the assertion, if any.
                Unsigned. Providers that never send one ignore it.

        Raises:
            ProviderAssertionInvalid: verification failed for any reason.
            ProviderUnavailable: key material could not be fetched.
        """
