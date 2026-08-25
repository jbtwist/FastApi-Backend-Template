# 2. Deliver tokens via both httponly cookies and the response body

Date: 2026-08-25

## Status

Accepted

## Context

`/auth/login` and `/auth/refresh` need to work for both the web client
(browser, cookie-based) and the mobile client (Expo app, which doesn't rely
on a cookie jar and authenticates with a bearer token instead). One backend
has to serve both.

## Decision

Both endpoints set httponly cookies (`access_token`, `refresh_token` — see
`backend.auth.cookies`) **and** return `access_token`/`refresh_token` in the
JSON response body (`TokenPairOut`). The web client can ignore the body and
rely on the cookies; the mobile client stores the body's tokens and sends
them as a bearer token (`backend.auth.dependencies.get_current_user` accepts
either an `Authorization: Bearer` header or the `access_token` cookie).

## Alternatives considered

- **Cookie-only** — more secure by default for the web client (tokens never
  land in JS-reachable response data), but doesn't work for the mobile app,
  which needs to hold and send the token itself.
- **Body-only (bearer)** — standard for mobile/API clients, but loses the
  httponly protection against token theft via XSS for the web client.

Both consumers exist from the start, so this wasn't a trade-off between the
two — both delivery modes are required.

## Consequences

- The response body is the more sensitive surface now: whatever stores it
  client-side (e.g. the mobile app's token storage) is trusted not to leak it,
  since httponly no longer protects that copy.
- Any future client only needs to pick one of the two mechanisms; nothing
  about the API forces a client to use both.
