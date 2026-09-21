"""Provider sign-in: opening an attempt, resolving a verified identity, and confirming a link.

A returning person is found by `(provider, provider_subject)` alone. A provider's
email is consulted only when that pair is unknown, and never signs anyone into an
existing account on its own. `sign_in_with_provider` has the full order.

Offering a link, or refusing an account that already has a provider, reveals that
the account exists, which password registration is careful never to do. It is
acceptable here because only someone who just proved control of that exact
address to the provider can reach those outcomes.
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.exc import IntegrityError

from backend.auth.config import AuthConfig
from backend.auth.models import User
from backend.auth.oauth.config import OAuthConfig
from backend.auth.oauth.contract import ProviderIdentity
from backend.auth.oauth.exceptions import (
    EmailLinkedToOtherProvider,
    InvalidOAuthLinkToken,
    InvalidOAuthState,
    OAuthLinkTokenExpired,
    ProviderEmailUnverified,
)
from backend.auth.oauth.repository import OAuthIdentityRepository, OAuthLinkTokenRepository
from backend.auth.oauth.state import SignInAttempt, SignInStateStore
from backend.auth.repository import RefreshTokenRepository, UserRepository
from backend.auth.security import generate_opaque_token, hash_opaque_token
from backend.auth.service import TokenPair, issue_token_pair
from backend.mail import service as mail_service
from backend.mail.models import EmailKind, EmailOutboxEntry
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

    Only a path starting with exactly one `/` is kept: a scheme, a host
    (`//evil.example`), a backslash or a control character would make the web
    return leg an open redirect.
    """
    if (
        not redirect_target
        or not redirect_target.startswith("/")
        or redirect_target.startswith("//")
        or "\\" in redirect_target
        or any(ord(char) < 0x20 or ord(char) == 0x7F for char in redirect_target)
    ):
        return DEFAULT_REDIRECT_TARGET
    return redirect_target


async def start_sign_in(
    state_store: SignInStateStore,
    *,
    provider: str,
    redirect_target: str | None,
    config: OAuthConfig,
) -> tuple[str, SignInAttempt]:
    """Open a sign-in attempt: mint a fresh `state` and `nonce` and store the attempt.

    `state` and `nonce` are independent CSPRNG values. The attempt lives for
    `OAUTH_STATE_TTL`.

    Returns:
        The `state` to hand the client, and the stored attempt.
    """
    state = generate_opaque_token()
    attempt = SignInAttempt(
        provider=provider,
        nonce=generate_opaque_token(),
        redirect_target=safe_redirect_target(redirect_target),
    )
    await state_store.save(state, attempt, ttl=config.OAUTH_STATE_TTL)
    return state, attempt


async def consume_sign_in_attempt(
    state_store: SignInStateStore, state: str, *, provider: str
) -> SignInAttempt:
    """Take the attempt stored under `state` out of the store, spending it.

    Raises:
        InvalidOAuthState: no such attempt (unknown, spent or expired), or it
            was started for a different provider than `provider`.
    """
    attempt = await state_store.consume(state)
    if attempt is None or attempt.provider != provider:
        raise InvalidOAuthState
    return attempt


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
       address, link the identity, sign in.
    4. The account already has a provider identity: refuse.
    5. The account's address was never verified: take it over, clearing its
       password and revoking its sessions, then sign in.
    6. Otherwise: mint an `oauth_link_token`, invalidating older ones, and queue
       the `oauth_link` email in the same transaction.

    A unique-constraint race on any insert re-runs the resolution once.

    Raises:
        ProviderEmailUnverified: the provider supplied no verified email.
        EmailLinkedToOtherProvider: the account already has a provider identity.
    """
    resolve = _Resolution(
        user_repo,
        identity_repo,
        refresh_token_repo,
        link_token_repo,
        outbox_repo,
        auth_config=auth_config,
        oauth_config=oauth_config,
        now=now,
    )
    try:
        return await resolve(identity)
    except IntegrityError:
        return await resolve(identity)


async def confirm_identity_link(
    link_token_repo: OAuthLinkTokenRepository,
    identity_repo: OAuthIdentityRepository,
    raw_token: str,
    *,
    now: datetime,
) -> None:
    """Redeem an `oauth_link_token`: attach its frozen identity to its user.

    Doesn't sign in: the email may be opened on a different device than the one
    that started the sign-in. The person signs in with the provider afterwards.

    Raises:
        InvalidOAuthLinkToken: the token is unknown, already used, or lost the
            race to be used.
        OAuthLinkTokenExpired: the token is at or past `expires_at`.
        EmailLinkedToOtherProvider: since the token was minted, the account got
            a provider identity, or this identity was linked to another account.
    """
    record = await link_token_repo.get_by_hash(hash_opaque_token(raw_token))
    if record is None or record.used_at is not None:
        raise InvalidOAuthLinkToken
    if record.expires_at <= now:
        raise OAuthLinkTokenExpired
    if not await link_token_repo.mark_used(record.id, used_at=now):
        raise InvalidOAuthLinkToken

    existing = await identity_repo.get_by_user_id(record.user_id)
    if existing is not None:
        raise EmailLinkedToOtherProvider(existing.provider)
    if await identity_repo.get_by_provider_subject(record.provider, record.provider_subject):
        raise EmailLinkedToOtherProvider(record.provider)

    try:
        await identity_repo.create(
            user_id=record.user_id,
            provider=record.provider,
            provider_subject=record.provider_subject,
            email_at_link=record.email_at_link,
            is_private_relay=record.is_private_relay,
            display_name=record.display_name,
        )
    except IntegrityError:
        raise EmailLinkedToOtherProvider(record.provider) from None


class _Resolution:
    """One run of the `sign_in_with_provider` rules, over a fixed set of repositories."""

    def __init__(
        self,
        user_repo: UserRepository,
        identity_repo: OAuthIdentityRepository,
        refresh_token_repo: RefreshTokenRepository,
        link_token_repo: OAuthLinkTokenRepository,
        outbox_repo: EmailOutboxRepository,
        *,
        auth_config: AuthConfig,
        oauth_config: OAuthConfig,
        now: datetime,
    ) -> None:
        self._user_repo = user_repo
        self._identity_repo = identity_repo
        self._refresh_token_repo = refresh_token_repo
        self._link_token_repo = link_token_repo
        self._outbox_repo = outbox_repo
        self._auth_config = auth_config
        self._oauth_config = oauth_config
        self._now = now

    async def __call__(self, identity: ProviderIdentity) -> SignedIn | LinkPending:
        link = await self._identity_repo.get_by_provider_subject(
            identity.provider, identity.subject
        )
        if link is not None:
            await self._identity_repo.mark_authenticated(link.id, authenticated_at=self._now)
            user = await self._user_repo.get_by_id(link.user_id)
            return await self._signed_in(user)

        if identity.email is None or not identity.email_verified:
            raise ProviderEmailUnverified(identity.provider)

        user = await self._user_repo.get_by_email(identity.email.strip().lower())
        if user is None:
            user = await self._user_repo.create(
                email=identity.email.strip().lower(), password_hash=None
            )
            await self._user_repo.mark_email_verified(user.id, verified_at=self._now)
            await self._link_identity(user, identity)
            return await self._signed_in(user)

        existing = await self._identity_repo.get_by_user_id(user.id)
        if existing is not None:
            raise EmailLinkedToOtherProvider(existing.provider)

        if user.email_verified_at is None:
            await self._user_repo.set_password_hash(
                user.id, password_hash=None, updated_at=self._now
            )
            await self._refresh_token_repo.revoke_all_for_user(user.id, revoked_at=self._now)
            await self._user_repo.mark_email_verified(user.id, verified_at=self._now)
            await self._link_identity(user, identity)
            return await self._signed_in(user)

        return LinkPending(outbox_entry=await self._offer_link(user, identity))

    async def _link_identity(self, user: User, identity: ProviderIdentity) -> None:
        await self._identity_repo.create(
            user_id=user.id,
            provider=identity.provider,
            provider_subject=identity.subject,
            email_at_link=identity.email,
            is_private_relay=identity.is_private_relay,
            display_name=identity.display_name,
        )

    async def _signed_in(self, user: User) -> SignedIn:
        pair = await issue_token_pair(
            self._refresh_token_repo, user, config=self._auth_config, now=self._now
        )
        return SignedIn(user=user, pair=pair)

    async def _offer_link(self, user: User, identity: ProviderIdentity) -> EmailOutboxEntry:
        raw_token = generate_opaque_token()
        await self._link_token_repo.invalidate_all_for_user(user.id, invalidated_at=self._now)
        await self._link_token_repo.create(
            user_id=user.id,
            token_hash=hash_opaque_token(raw_token),
            expires_at=self._now + self._oauth_config.OAUTH_LINK_TOKEN_EXP,
            identity=identity,
        )
        return await mail_service.enqueue_email(
            self._outbox_repo,
            user_id=user.id,
            email=user.email,
            token=raw_token,
            created_at=self._now,
            kind=EmailKind.OAUTH_LINK,
        )
