# 7. Concurrent refresh handling

Date: 2026-09-18

## Status

Accepted

## Context

ADR-0001 established that refresh tokens are single-use and rotate on every `/auth/refresh` call, with reuse detection revoking the entire family. In practice, concurrent requests (e.g., from multiple browser tabs) using the same refresh token are common and should not be treated as theft (token reuse).

## Decision

We introduce `REFRESH_TOKEN_REUSE_GRACE` (10s) to allow concurrent refreshes. 

1. If a refresh token is presented, the backend marks it as used.
2. If another request presents the same token, the backend checks if it arrived within `REFRESH_TOKEN_REUSE_GRACE` of the first request.
3. If it did, it raises `ConcurrentRefresh` (`409 Conflict`), and no cookies are modified.
4. If it arrives later, it is treated as token reuse (ADR-0001), and the entire family is revoked.

The web client is updated to recognize `409` as a signal to retry the original request, as it likely already holds the new cookies from the winning refresh request. Native clients treat `409` as a failed refresh.

## Consequences

- Improved UX for browser users with multiple tabs.
- Slightly increased window of vulnerability for stolen tokens (from instant detection to 10s grace).
- Clients need to handle `409 Conflict` on `/auth/refresh`.
