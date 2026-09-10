# 1. Refresh token rotation with family-based reuse detection

Date: 2026-08-25

## Status

Accepted

## Context

The app is used from both a mobile client and a web client, so a single user
can have multiple concurrent sessions authenticated in different ways
(browser cookie jar vs. a mobile app holding tokens itself). A stolen refresh
token needs to be detectable and containable without forcing every other
device to re-authenticate.

## Decision

Refresh tokens are single-use and rotate on every `/auth/refresh` call. All
tokens produced by rotating from one login share that login's `family_id`
(`backend.auth.service.issue_token_pair` starts a new family; `rotate_refresh_token`
carries it forward). If a token that was already used gets presented again,
the entire family is revoked.

Because each login gets its own family, revoking one compromised session's
family doesn't touch the user's other sessions.

## Alternatives considered

- **Single long-lived refresh token, no rotation** — simplest to implement,
  but a stolen token stays valid until it expires; there's no signal that
  theft happened and no way to react to it.
- **Server-side session store (e.g. Redis), no JWT** — every request checked
  against shared state, trivial to revoke instantly, but adds a lookup to
  every authenticated request and state to keep consistent across processes.

## Consequences

- A device that's offline across a token rotation permanently loses its
  session on reconnect — the app needs to handle a 401 from `/auth/refresh`
  by prompting re-login, not just retrying.
- Reuse detection depends on `mark_used` racing correctly under concurrent
  refresh calls for the same token (`SqlRefreshTokenRepository.mark_used`
  uses a conditional `UPDATE ... WHERE used_at IS NULL` for this); a second
  concurrent caller that loses the race is treated as reuse, not as a benign
  retry.
