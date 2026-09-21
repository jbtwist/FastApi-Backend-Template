"""Cross-origin access for browser clients.

The web client calls this API from its own origin with cookies, so every
response, including errors, needs CORS headers, or the browser hides it from
the client and a failed `fetch` looks like being offline.

Unhandled exceptions are the one response CORS cannot reach: Starlette answers
those from `ServerErrorMiddleware`, outside every middleware added here, so
`ServerErrorAsResponse` answers them from inside CORS instead.
"""

from collections.abc import Sequence

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

ALLOWED_METHODS = ["GET", "POST", "PATCH", "DELETE", "OPTIONS"]
ALLOWED_HEADERS = ["Accept", "Authorization", "Content-Type"]
# `Retry-After` is not CORS-safelisted; unexposed, the client can't read the 429 countdown.
EXPOSED_HEADERS = ["Retry-After"]
PREFLIGHT_MAX_AGE_SECONDS = 600


class ServerErrorAsResponse:
    """Answer an unhandled exception with a plain 500, from inside `CORSMiddleware`."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False

        async def send_tracking_start(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, send_tracking_start)
        except Exception:
            if not response_started:
                response = PlainTextResponse("Internal Server Error", status_code=500)
                await response(scope, receive, send)
            raise


def add_cors(app: FastAPI, *, allowed_origins: Sequence[str]) -> None:
    """Allow credentialed calls from `allowed_origins`.

    `allow_credentials` with a wildcard origin would let any site make
    authenticated calls, so `Settings` rejects `*`.
    """
    app.add_middleware(ServerErrorAsResponse)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(allowed_origins),
        allow_credentials=True,
        allow_methods=ALLOWED_METHODS,
        allow_headers=ALLOWED_HEADERS,
        expose_headers=EXPOSED_HEADERS,
        max_age=PREFLIGHT_MAX_AGE_SECONDS,
    )
