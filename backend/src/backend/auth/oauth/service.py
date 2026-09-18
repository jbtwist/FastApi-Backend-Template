"""Provider sign-in: opening an attempt, resolving a verified identity, and confirming a link.

A returning person is found by `(provider, provider_subject)` alone. A provider's
email is consulted only when that pair is unknown, and only once the provider has
vouched for it (`email_verified`); even then it never signs anyone into an
existing account on its own. An account whose address was never verified is
taken over, since nobody has proven they own it. A verified account without a
provider gets a link confirmation email instead, and one that already has a
provider is refused: an account holds at most one.

That second-to-last pair of outcomes reveals that an account exists, which
password registration is careful never to do. It is acceptable here because
only someone who just proved control of that exact address to the provider can
reach them.
"""

from dataclasses import dataclass
from datetime import datetime

from backend.auth.config import AuthConfig
from backend.auth.models import User
from backend.auth.oauth.config import OAuthConfig
from backend.auth.oauth.contract import ProviderIdentity
from backend.auth.oauth.repository import OAuthIdentityRepository, OAuthLinkTokenRepository
from backend.auth.oauth.state import SignInAttempt, SignInStateStore
from backend.auth.repository import RefreshTokenRepository, UserRepository
from backend.auth.service import TokenPair
from backend.mail.models import EmailOutboxEntry
from backend.mail.service import EmailOutboxRepository

DEFAULT_REDIRECT_TARGET = "/"


@dataclass(frozen=True, slots=True)
class SignedIn:
    """A session was issued for `user`."""

    user: User
    pair: TokenPair


@dataclass(frozen=True, slots=True)
class LinkPending:
    """A link confirmation email was queued; `outbox_entry` is what to dispatch."""

    outbox_entry: EmailOutboxEntry


def safe_redirect_target(redirect_target: str | None) -> str:
    """Return `redirect_target` if it is an app-relative path, else `DEFAULT_REDIRECT_TARGET`.

    Only a path starting with exactly one `/` is kept: anything with a scheme, a
    host (`//evil.example`), a backslash or a control character would let the
    web return leg be used as an open redirect.
    """
    raise NotImplementedError


async def start_sign_in(
    state_store: SignInStateStore,
    *,
    provider: str,
    redirect_target: str | None,
    config: OAuthConfig,
) -> tuple[str, SignInAttempt]:
    """Open a sign-in attempt: mint a fresh `state` and `nonce` and store the attempt.

    `state` and `nonce` are independent values from a CSPRNG. The attempt lives
    for `OAUTH_STATE_TTL`, and its `redirect_target` has already passed
    `safe_redirect_target`.

    Returns:
        The `state` to hand the client, and the stored attempt.
    """
    raise NotImplementedError


async def consume_sign_in_attempt(
    state_store: SignInStateStore, state: str, *, provider: str
) -> SignInAttempt:
    """Take the attempt stored under `state` out of the store, spending it.

    Raises:
        InvalidOAuthState: no such attempt (unknown, spent or expired), or it
            was started for a different provider than `provider`.
    """
    raise NotImplementedError


async def sign_in_with_provider(
    user_repo: UserRepository,
    identity_repo: OAuthIdentityRepository,
    refresh_token_repo: RefreshTokenRepository,
    link_token_repo: OAuthLinkTokenRepository,
    outbox_repo: EmailOutboxRepository,
    identity: ProviderIdentity,
    *,
    auth_config: AuthConfig,
    oauth_config: OAuthConfig,
    now: datetime,
) -> SignedIn | LinkPending:
    """Resolve a verified provider identity to a session, a new account, or a pending link.

    In order:

    1. `(provider, provider_subject)` already linked: sign in as that user,
       whatever the email now says.
    2. No email, or one the provider didn't verify: refuse.
    3. No account has the email: create one with no password and a verified
       address, link the identity, and sign in.
    4. The account already has a provider identity: refuse.
    5. The account's address was never verified: take it over. Its password is
       cleared, its sessions revoked, its address marked verified, and the
       identity linked, then sign in.
    6. Otherwise: mint an `oauth_link_token`, invalidating older ones, and
       queue the `oauth_link` email in the same transaction.

    A unique-constraint race on any insert re-runs the resolution once.

    Raises:
        ProviderEmailUnverified: the provider supplied no verified email.
        EmailLinkedToOtherProvider: the account already has a provider identity.
    """
    raise NotImplementedError


async def confirm_identity_link(
    link_token_repo: OAuthLinkTokenRepository,
    identity_repo: OAuthIdentityRepository,
    raw_token: str,
    *,
    now: datetime,
) -> None:
    """Redeem an `oauth_link_token`: attach its frozen identity to its user.

    Doesn't sign in: the email may be opened on another device than the one
    that started the sign-in. The person signs in with the provider afterwards.

    Raises:
        InvalidOAuthLinkToken: the token is unknown, already used, or lost the
            race to be used.
        OAuthLinkTokenExpired: the token is at or past `expires_at`.
        EmailLinkedToOtherProvider: since the token was minted, the account got
            a provider identity, or this identity was linked to another account.
    """
    raise NotImplementedError
