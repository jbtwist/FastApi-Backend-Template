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
from urllib.parse import urlencode

from fastapi import APIRouter, Cookie, Depends, Response, status
from fastapi.responses import JSONResponse, RedirectResponse

from backend.auth.cookies import set_token_cookies
from backend.auth.dependencies import AuthConfigDep, RefreshTokenRepoDep, UserRepoDep
from backend.auth.oauth import service
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
from backend.auth.oauth.schemas import (
    OAuthLinkConfirmIn,
    OAuthLinkPendingOut,
    OAuthNativeIn,
    OAuthProvidersOut,
    OAuthStartIn,
    OAuthStartOut,
)
from backend.auth.schemas import LoginOut
from backend.mail.config import mail_settings
from backend.mail.dependencies import EmailOutboxRepoDep
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
        secure=auth_config.COOKIE_SECURE,
        samesite="lax",
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
    """Finish a browser sign-in and redirect back to the frontend.

    The `state` must match the `oauth_state` cookie as well as a stored attempt,
    so a callback link can't be replayed into another browser. Every outcome is
    a redirect: to the attempt's `redirect_target` with session cookies, or to
    the sign-in screen with an `oauth_error` or `oauth_notice` flag.
    """
    try:
        if error is not None:
            raise _ProviderRefused(error)
        if not (code and state and oauth_state and secrets.compare_digest(state, oauth_state)):
            raise InvalidOAuthState
        attempt = await service.consume_sign_in_attempt(state_store, state, provider=provider.name)
        identity = await provider.exchange_redirect(
            code=code, redirect_uri=_callback_url(provider.name), nonce=attempt.nonce
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
        flag = "cancelled" if exc.error == "access_denied" else "failed"
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
        secure=auth_config.COOKIE_SECURE,
        samesite="lax",
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


class _ProviderRefused(Exception):
    """The provider sent the browser back with an `error` instead of a `code`."""

    def __init__(self, error: str) -> None:
        super().__init__(error)
        self.error = error
