"""Cross-origin access for browser clients.

The web client is served from its own origin (the Expo web build) and talks to
this API with cookies, so every response — including error responses — needs
CORS headers. Without them the browser rejects the response before the client
sees it, and a failed `fetch` is indistinguishable from being offline.
"""

from collections.abc import Sequence

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

ALLOWED_METHODS = ["GET", "POST", "PATCH", "DELETE", "OPTIONS"]
ALLOWED_HEADERS = ["Accept", "Authorization", "Content-Type"]
# `Retry-After` is not a CORS-safelisted response header: without exposing it,
# the client can't read the rate-limit countdown off a 429.
EXPOSED_HEADERS = ["Retry-After"]
PREFLIGHT_MAX_AGE_SECONDS = 600


def add_cors(app: FastAPI, *, allowed_origins: Sequence[str]) -> None:
    """Allow credentialed calls from `allowed_origins`.

    Call this last: `add_middleware` prepends, so the middleware added last runs
    outermost and a response built by an inner middleware (a 429 from the rate
    limiter) still gets its CORS headers.

    Origins are always an explicit list — `allow_credentials` with a wildcard
    would let any site make authenticated calls, so `Settings` rejects `*`.
    """
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(allowed_origins),
        allow_credentials=True,
        allow_methods=ALLOWED_METHODS,
        allow_headers=ALLOWED_HEADERS,
        expose_headers=EXPOSED_HEADERS,
        max_age=PREFLIGHT_MAX_AGE_SECONDS,
    )
