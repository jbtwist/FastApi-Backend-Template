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
- Every refresh writes to Postgres, as described below.

### Database load from refreshes

Every `POST /auth/refresh` costs Postgres one indexed read and two writes: an
`UPDATE` that marks the old token used (`mark_used`, which is also what makes
reuse detection possible) and an `INSERT` for its replacement.

`ACCESS_TOKEN_EXP` sets how often that happens, not `REFRESH_TOKEN_EXP`. A
client refreshes when its access token expires, so the load is roughly:

```text
refreshes per second ≈ active sessions / ACCESS_TOKEN_EXP in seconds
```

At the default 15 minutes, 100,000 active sessions make about 110 refreshes,
or 220 small writes, per second. A single Postgres instance handles that
comfortably. When you scale out, you'll usually hit the database connection
limit long before this table becomes a problem.

If refresh traffic does become a problem, you have two options:

- **Raise `ACCESS_TOKEN_EXP`.** Refresh load falls in proportion: 30 minutes
  halves it. It's a config change with no code involved. The cost is that
  access tokens are stateless JWTs and can't be revoked, so logout, a password
  reset, or a revoked family takes up to `ACCESS_TOKEN_EXP` to stop a token
  that was already issued. Changing `REFRESH_TOKEN_EXP` only changes how long
  an idle session survives, not the load.
- **Store refresh tokens in Redis.** This moves the writes off Postgres.
  Services only see the `RefreshTokenRepository` protocol, so it means
  writing a new repository, not changing the service. `mark_used` has to stay
  atomic, for example with `SET ... NX` or a Lua script, or two concurrent
  refreshes could both win. The trade-offs:
    - **Durability.** If Redis loses data (a restart without persistence, or
      eviction under memory pressure), the affected tokens become invalid and
      those users are signed out. Run it with AOF persistence and
      `maxmemory-policy noeviction`, separately from the Celery broker and rate
      limiter.
    - **Transactions.** Revocations no longer commit in the same transaction
      as the Postgres change that triggers them. Today a password reset changes
      the password and revokes every session atomically. With Redis those
      become two steps, and a failure between them leaves the old sessions
      alive.
    - **Operations.** You get one more stateful store to back up and monitor.

Neither option is implemented beyond the config knob. Raise `ACCESS_TOKEN_EXP`
first.
