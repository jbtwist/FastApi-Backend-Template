"""Cross-origin access for browser clients.

The web client is served from its own origin (the Expo web build) and talks to
this API with cookies, so every response — including error responses — needs
CORS headers. Without them the browser rejects the response before the client
sees it, and a failed `fetch` is indistinguishable from being offline.

An unhandled exception is the one response CORS cannot reach on its own:
Starlette answers it from `ServerErrorMiddleware`, which always sits outside
every middleware added here, so the 500 would go out with no CORS headers at
all. `ServerErrorAsResponse` answers it from inside CORS instead.
"""

from collections.abc import Sequence

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

ALLOWED_METHODS = ["GET", "POST", "PATCH", "DELETE", "OPTIONS"]
ALLOWED_HEADERS = ["Accept", "Authorization", "Content-Type"]
# `Retry-After` is not a CORS-safelisted response header: without exposing it,
# the client can't read the rate-limit countdown off a 429.
EXPOSED_HEADERS = ["Retry-After"]
PREFLIGHT_MAX_AGE_SECONDS = 600


class ServerErrorAsResponse:
    """Answer an unhandled exception with a plain 500, from inside `CORSMiddleware`.

    Install it directly inside CORS, so the headers CORS adds reach this 500
    too.

    The exception is re-raised after the response is sent, so the server logs
    it as it always did; `ServerErrorMiddleware` then sees a response already
    started and adds nothing of its own. An exception raised after the response
    started is left alone — there is nothing left to answer with.
    """

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

    Call this last: `add_middleware` prepends, so the middleware added last runs
    outermost and a response built by an inner middleware (a 429 from the rate
    limiter, or the 500 from `ServerErrorAsResponse`) still gets its CORS headers.

    Origins are always an explicit list — `allow_credentials` with a wildcard
    would let any site make authenticated calls, so `Settings` rejects `*`.
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
