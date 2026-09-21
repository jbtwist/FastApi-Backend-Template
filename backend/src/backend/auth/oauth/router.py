"""`/auth/oauth` endpoints, mounted onto the `/auth` router.

Two routes into the same sign-in. Native clients call `start`, run the platform
SDK with the returned `nonce`, and post the assertion to `native`, getting JSON
back. Browsers go to `authorize`, are sent to the provider, and come back
through `callback`, which answers with a redirect to the frontend: session
cookies set on success, an `oauth_error` or `oauth_notice` flag otherwise.
"""

import secrets
from datetime import UTC, datetime
from typing import Annotated
from urllib.parse import parse_qsl, urlencode

from fastapi import APIRouter, Cookie, Depends, Request, Response, status
from fastapi.responses import JSONResponse, RedirectResponse

from backend.auth.config import AuthConfig
from backend.auth.cookies import set_token_cookies
from backend.auth.dependencies import AuthConfigDep, RefreshTokenRepoDep, UserRepoDep
from backend.auth.oauth import service
from backend.auth.oauth.config import OAuthConfig
from backend.auth.oauth.contract import OAuthProvider
from backend.auth.oauth.dependencies import (
    EnabledProvidersDep,
    OAuthConfigDep,
    OAuthIdentityRepoDep,
    OAuthLinkTokenRepoDep,
    ProviderDep,
    StateStoreDep,
)
from backend.auth.oauth.exceptions import (
    EmailLinkedToOtherProvider,
    InvalidOAuthState,
    ProviderAssertionInvalid,
    ProviderEmailUnverified,
    ProviderUnavailable,
)
from backend.auth.oauth.repository import OAuthIdentityRepository, OAuthLinkTokenRepository
from backend.auth.oauth.schemas import (
    OAuthLinkConfirmIn,
    OAuthLinkPendingOut,
    OAuthNativeIn,
    OAuthProvidersOut,
    OAuthStartIn,
    OAuthStartOut,
)
from backend.auth.oauth.state import SignInStateStore
from backend.auth.repository import RefreshTokenRepository, UserRepository
from backend.auth.schemas import LoginOut
from backend.mail.config import mail_settings
from backend.mail.dependencies import EmailOutboxRepoDep
from backend.mail.service import EmailOutboxRepository
from backend.mail.tasks import queue_dispatch_email
from backend.rate_limit import rate_limit

router = APIRouter(prefix="/oauth")

OAUTH_STATE_COOKIE = "oauth_state"
_OAUTH_STATE_COOKIE_PATH = "/auth/oauth"
_SIGN_IN_PATH = "/sign-in"


def _callback_url(provider_name: str) -> str:
    return f"{mail_settings.API_BASE_URL}/auth/oauth/{provider_name}/callback"


def _sign_in_url(**flags: str) -> str:
    return f"{mail_settings.FRONTEND_BASE_URL}{_SIGN_IN_PATH}?{urlencode(flags)}"


def _oauth_state_cookie_site(config: AuthConfig) -> dict[str, object]:
    """How the `oauth_state` cookie travels.

    A provider that posts the result back (Apple) returns the browser from its
    own site, and a `SameSite=Lax` cookie is not sent on a cross-site POST — the
    binding would be lost and every such sign-in refused. `None` restores it,
    and browsers only accept `None` together with `Secure`, so plain HTTP (local
    development) keeps `Lax`: there the callback is same-site anyway.
    """
    if config.COOKIE_SECURE:
        return {"secure": True, "samesite": "none"}
    return {"secure": False, "samesite": "lax"}


def _login_out(result: service.SignedIn) -> LoginOut:
    return LoginOut(
        id=result.user.id,
        email=result.user.email,
        email_verified=True,
        access_token=result.pair.access_token,
        refresh_token=result.pair.refresh_token,
    )


@router.get("/providers", response_model=OAuthProvidersOut)
async def providers(enabled: EnabledProvidersDep) -> OAuthProvidersOut:
    """List the providers this deployment offers, in `OAUTH_ENABLED_PROVIDERS` order."""
    return OAuthProvidersOut(providers=list(enabled))


@router.post(
    "/{provider}/start",
    response_model=OAuthStartOut,
    dependencies=[Depends(rate_limit("10/minute"))],
)
async def start(
    provider: ProviderDep,
    state_store: StateStoreDep,
    config: OAuthConfigDep,
    payload: OAuthStartIn | None = None,
) -> OAuthStartOut:
    """Open a native sign-in attempt.

    The `nonce` goes to the platform SDK; the `state` comes back with the assertion to `native`.
    """
    state, attempt = await service.start_sign_in(
        state_store,
        provider=provider.name,
        redirect_target=payload.redirect_target if payload else None,
        config=config,
    )
    return OAuthStartOut(
        state=state,
        nonce=attempt.nonce,
        expires_in=int(config.OAUTH_STATE_TTL.total_seconds()),
    )


@router.post(
    "/{provider}/native",
    response_model=LoginOut,
    responses={status.HTTP_202_ACCEPTED: {"model": OAuthLinkPendingOut}},
    dependencies=[Depends(rate_limit("10/minute"))],
)
async def native(
    payload: OAuthNativeIn,
    response: Response,
    provider: ProviderDep,
    state_store: StateStoreDep,
    user_repo: UserRepoDep,
    identity_repo: OAuthIdentityRepoDep,
    refresh_token_repo: RefreshTokenRepoDep,
    link_token_repo: OAuthLinkTokenRepoDep,
    outbox_repo: EmailOutboxRepoDep,
    auth_config: AuthConfigDep,
    oauth_config: OAuthConfigDep,
) -> LoginOut | JSONResponse:
    """Trade a platform SDK's assertion for a session, or a `202` if a link email went out instead.

    Sets the token cookies and returns the tokens, exactly as `POST /auth/login`.
    """
    attempt = await service.consume_sign_in_attempt(
        state_store, payload.state, provider=provider.name
    )
    identity = await provider.exchange_native(assertion=payload.assertion, nonce=attempt.nonce)
    result = await service.sign_in_with_provider(
        user_repo,
        identity_repo,
        refresh_token_repo,
        link_token_repo,
        outbox_repo,
        identity,
        auth_config=auth_config,
        oauth_config=oauth_config,
        now=datetime.now(UTC),
    )
    if isinstance(result, service.LinkPending):
        await queue_dispatch_email(str(result.outbox_entry.id))
        return JSONResponse(
            OAuthLinkPendingOut().model_dump(), status_code=status.HTTP_202_ACCEPTED
        )

    set_token_cookies(response, result.pair, config=auth_config)
    return _login_out(result)


@router.get("/{provider}/authorize", dependencies=[Depends(rate_limit("10/minute"))])
async def authorize(
    provider: ProviderDep,
    state_store: StateStoreDep,
    auth_config: AuthConfigDep,
    oauth_config: OAuthConfigDep,
    redirect_target: str | None = None,
) -> RedirectResponse:
    """Send the browser to the provider, binding it to the attempt with the `oauth_state` cookie."""
    state, attempt = await service.start_sign_in(
        state_store, provider=provider.name, redirect_target=redirect_target, config=oauth_config
    )
    response = RedirectResponse(
        provider.authorization_url(
            state=state, nonce=attempt.nonce, redirect_uri=_callback_url(provider.name)
        ),
        status_code=status.HTTP_302_FOUND,
    )
    response.set_cookie(
        key=OAUTH_STATE_COOKIE,
        value=state,
        max_age=int(oauth_config.OAUTH_STATE_TTL.total_seconds()),
        path=_OAUTH_STATE_COOKIE_PATH,
        httponly=True,
        **_oauth_state_cookie_site(auth_config),
    )
    return response


@router.get("/{provider}/callback", dependencies=[Depends(rate_limit("10/minute"))])
async def callback(
    provider: ProviderDep,
    state_store: StateStoreDep,
    user_repo: UserRepoDep,
    identity_repo: OAuthIdentityRepoDep,
    refresh_token_repo: RefreshTokenRepoDep,
    link_token_repo: OAuthLinkTokenRepoDep,
    outbox_repo: EmailOutboxRepoDep,
    auth_config: AuthConfigDep,
    oauth_config: OAuthConfigDep,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    oauth_state: Annotated[str | None, Cookie()] = None,
) -> RedirectResponse:
    """Finish a browser sign-in that came back as a redirect, and land on the frontend.

    The `state` must match the `oauth_state` cookie as well as a stored attempt,
    so a callback link can't be replayed into another browser. Every outcome is
    a redirect: to the attempt's `redirect_target` with session cookies, or to
    the sign-in screen with an `oauth_error` or `oauth_notice` flag.
    """
    return await _complete_callback(
        provider,
        state_store,
        user_repo,
        identity_repo,
        refresh_token_repo,
        link_token_repo,
        outbox_repo,
        auth_config=auth_config,
        oauth_config=oauth_config,
        code=code,
        state=state,
        error=error,
        user_details=None,
        oauth_state=oauth_state,
    )


@router.post("/{provider}/callback", dependencies=[Depends(rate_limit("10/minute"))])
async def callback_form_post(
    request: Request,
    provider: ProviderDep,
    state_store: StateStoreDep,
    user_repo: UserRepoDep,
    identity_repo: OAuthIdentityRepoDep,
    refresh_token_repo: RefreshTokenRepoDep,
    link_token_repo: OAuthLinkTokenRepoDep,
    outbox_repo: EmailOutboxRepoDep,
    auth_config: AuthConfigDep,
    oauth_config: OAuthConfigDep,
    oauth_state: Annotated[str | None, Cookie()] = None,
) -> RedirectResponse:
    """The same return leg, for a provider that posts the result back as a form.

    Apple does: it posts `code` and `state`, and on the very first sign-in a
    `user` field carrying the person's name, which its ID token never repeats.
    The urlencoded body is parsed here rather than declared with `Form(...)`,
    which would pull in a multipart library this app doesn't need.
    """
    form = dict(parse_qsl((await request.body()).decode(), keep_blank_values=True))

    return await _complete_callback(
        provider,
        state_store,
        user_repo,
        identity_repo,
        refresh_token_repo,
        link_token_repo,
        outbox_repo,
        auth_config=auth_config,
        oauth_config=oauth_config,
        code=form.get("code"),
        state=form.get("state"),
        error=form.get("error"),
        user_details=form.get("user"),
        oauth_state=oauth_state,
    )


async def _complete_callback(
    provider: OAuthProvider,
    state_store: SignInStateStore,
    user_repo: UserRepository,
    identity_repo: OAuthIdentityRepository,
    refresh_token_repo: RefreshTokenRepository,
    link_token_repo: OAuthLinkTokenRepository,
    outbox_repo: EmailOutboxRepository,
    *,
    auth_config: AuthConfig,
    oauth_config: OAuthConfig,
    code: str | None,
    state: str | None,
    error: str | None,
    user_details: str | None,
    oauth_state: str | None,
) -> RedirectResponse:
    """Verify the returned attempt, sign in, and turn every outcome into a redirect."""
    try:
        if error is not None:
            raise _ProviderRefused(error)
        if not (code and state and oauth_state and secrets.compare_digest(state, oauth_state)):
            raise InvalidOAuthState
        attempt = await service.consume_sign_in_attempt(state_store, state, provider=provider.name)
        identity = await provider.exchange_redirect(
            code=code,
            redirect_uri=_callback_url(provider.name),
            nonce=attempt.nonce,
            user_details=user_details,
        )
        result = await service.sign_in_with_provider(
            user_repo,
            identity_repo,
            refresh_token_repo,
            link_token_repo,
            outbox_repo,
            identity,
            auth_config=auth_config,
            oauth_config=oauth_config,
            now=datetime.now(UTC),
        )
    except _ProviderRefused as exc:
        flag = "cancelled" if exc.error in _CANCELLED_BY_PERSON else "failed"
        response = RedirectResponse(_sign_in_url(oauth_error=flag), status.HTTP_302_FOUND)
    except InvalidOAuthState, ProviderAssertionInvalid:
        response = RedirectResponse(_sign_in_url(oauth_error="failed"), status.HTTP_302_FOUND)
    except ProviderUnavailable:
        response = RedirectResponse(_sign_in_url(oauth_error="unavailable"), status.HTTP_302_FOUND)
    except ProviderEmailUnverified:
        response = RedirectResponse(
            _sign_in_url(oauth_error="email_not_verified_by_provider"), status.HTTP_302_FOUND
        )
    except EmailLinkedToOtherProvider as exc:
        response = RedirectResponse(
            _sign_in_url(
                oauth_error="email_linked_to_other_provider", linked_provider=exc.linked_provider
            ),
            status.HTTP_302_FOUND,
        )
    else:
        if isinstance(result, service.LinkPending):
            await queue_dispatch_email(str(result.outbox_entry.id))
            response = RedirectResponse(
                _sign_in_url(oauth_notice="link_email_sent"), status.HTTP_302_FOUND
            )
        else:
            response = RedirectResponse(
                f"{mail_settings.FRONTEND_BASE_URL}{attempt.redirect_target}",
                status.HTTP_302_FOUND,
            )
            set_token_cookies(response, result.pair, config=auth_config)

    response.delete_cookie(
        OAUTH_STATE_COOKIE,
        path=_OAUTH_STATE_COOKIE_PATH,
        httponly=True,
        **_oauth_state_cookie_site(auth_config),
    )
    return response


@router.post(
    "/link/confirm",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(rate_limit("10/minute"))],
)
async def confirm_link(
    payload: OAuthLinkConfirmIn,
    link_token_repo: OAuthLinkTokenRepoDep,
    identity_repo: OAuthIdentityRepoDep,
) -> None:
    """Redeem an emailed `oauth_link_token`.

    Doesn't sign in: the person signs in with the provider next.
    """
    await service.confirm_identity_link(
        link_token_repo, identity_repo, payload.token, now=datetime.now(UTC)
    )


#: What each provider calls "the person pressed Cancel": a normal act, not a failure.
_CANCELLED_BY_PERSON = frozenset({"access_denied", "user_cancelled_authorize"})


class _ProviderRefused(Exception):
    """The provider sent the browser back with an `error` instead of a `code`."""

    def __init__(self, error: str) -> None:
        super().__init__(error)
        self.error = error
