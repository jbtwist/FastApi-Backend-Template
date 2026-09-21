"""Maps the JSON OAuth endpoints' failures to HTTP responses in one place.

The web callback doesn't reach these: it answers every failure with a redirect
back to the sign-in screen, carrying an `oauth_error` flag instead of a body.
"""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from backend.auth.oauth.exceptions import (
    EmailLinkedToOtherProvider,
    InvalidOAuthLinkToken,
    InvalidOAuthState,
    OAuthLinkTokenExpired,
    ProviderAssertionInvalid,
    ProviderEmailUnverified,
    ProviderNotConfigured,
    ProviderUnavailable,
)

_HTTP_BY_ERROR: dict[type[Exception], tuple[int, str]] = {
    ProviderNotConfigured: (status.HTTP_404_NOT_FOUND, "Unknown provider"),
    InvalidOAuthState: (status.HTTP_401_UNAUTHORIZED, "Sign-in attempt invalid or expired"),
    ProviderAssertionInvalid: (status.HTTP_401_UNAUTHORIZED, "Provider sign-in failed"),
    ProviderUnavailable: (status.HTTP_503_SERVICE_UNAVAILABLE, "Provider unavailable"),
    ProviderEmailUnverified: (status.HTTP_403_FORBIDDEN, "Provider did not verify the email"),
    InvalidOAuthLinkToken: (status.HTTP_400_BAD_REQUEST, "Invalid or expired link token"),
    OAuthLinkTokenExpired: (status.HTTP_400_BAD_REQUEST, "Invalid or expired link token"),
}


async def _handle(request: Request, exc: Exception) -> JSONResponse:
    status_code, detail = _HTTP_BY_ERROR[type(exc)]
    return JSONResponse({"detail": detail}, status_code=status_code)


async def _handle_linked_elsewhere(
    request: Request, exc: EmailLinkedToOtherProvider
) -> JSONResponse:
    """A `409` naming the linked provider as data, for the client to put in its own words."""
    return JSONResponse(
        {"detail": "Email linked to another provider", "linked_provider": exc.linked_provider},
        status_code=status.HTTP_409_CONFLICT,
    )


def add_oauth_error_handlers(app: FastAPI) -> None:
    for exc_type in _HTTP_BY_ERROR:
        app.add_exception_handler(exc_type, _handle)
    app.add_exception_handler(EmailLinkedToOtherProvider, _handle_linked_elsewhere)
