"""The provider seam: what every sign-in provider adapter implements, and all shared code sees.

An adapter verifies an assertion before trusting any of it: the signature against
current JWKS, `iss`, `aud` (a set, since providers ship several client
identities), `exp` with 60 s leeway, and the echoed `nonce`. It caches its JWKS,
raises rather than returns on failure, never puts a raw assertion, code, secret or
key into an exception or a log, and constructs without I/O so a misconfigured
provider can't stop the app booting.
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ProviderIdentity:
    """What one verified provider assertion says about a person.

    Produced only after signature, issuer, audience, expiry and nonce have all
    been checked. Every field is provider-supplied data and none of it is
    rendered to a user. `subject` is what finds a returning person; a verified
    `email` only ever finds an account to create or to offer a link to, never
    one to sign in to (see `backend.auth.oauth.service.sign_in_with_provider`).
    """

    provider: str
    subject: str
    email: str | None
    email_verified: bool
    is_private_relay: bool
    display_name: str | None


class OAuthProvider(Protocol):
    """One third-party sign-in provider.

    Everything that differs between providers lives behind this: how the client
    is identified, how a client credential is formed, how the browser result
    comes back, and whether a name is ever supplied. Shared code knows only
    these three methods and `ProviderIdentity`.
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
                on the first sign-in, passed on untouched. A provider may read a
                `display_name` from it, and nothing else.

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
