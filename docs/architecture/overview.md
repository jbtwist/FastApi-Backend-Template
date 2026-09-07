# Architecture overview

`backend/` is a FastAPI app (`backend.main:app`) with two modules so far:

- **`backend.auth`** — registration, login, JWT access tokens, refresh token
  rotation, email verification, and password reset. See the [reference](../reference/auth.md).
- **`backend.mail`** — a durable outbox for outbound email, dispatched by a
  Celery worker. See the [reference](../reference/mail.md).

Redis backs rate limiting (`fastapi-redis-sdk`) and Celery's broker/result
backend. Persistence is via SQLAlchemy + Alembic migrations
(`backend/migrations`), on Postgres (`asyncpg`).

`frontend/` is a separate Expo app; it's the "mobile" client referenced in
the auth decisions below, alongside a browser-based web client. It features an
internationalization (i18n) subsystem that detects device locales, provides
translated strings, and persists user language preferences.

## Authentication

Login and refresh both return an access token (short-lived JWT, 15 min) and a
refresh token (opaque, 30 days, single-use, rotates on every refresh). Both
are set as httponly cookies *and* returned in the response body, so browser
and non-browser clients can each use the delivery mechanism that fits them.
See [ADR 2](decisions/0002-dual-cookie-and-body-token-delivery.md).

The frontend manages user authentication state through an `auth-context` state machine (see `frontend/src/auth/auth-context.tsx`). This machine orchestrates the `ApiClient` to handle:
- **Platform-specific transport**: Attaches the access token as a `Bearer` header for native, or uses `credentials: 'include'` for web.
- **Single-flight refresh**: Coalesces concurrent 401 errors into a single `/auth/refresh` call and retries the original request, ensuring a smooth session transition.
- **Error mapping**: Translates API failures into typed `AuthApiError` objects for consistent UI feedback.
- **Session management**: Handles bootstrapping, login, registration, logout, and session expiration notices.

It also manages ephemeral state for the email verification flow via `pending-verification` (see `frontend/src/auth/pending-verification.ts`), which stores the email address and timestamp of the last verification email sent to throttle resend requests.

Refresh tokens from one login share a `family_id`. Reusing an already-used
refresh token revokes its whole family — this detects a stolen refresh token
without signing out the user's other sessions. See
[ADR 1](decisions/0001-refresh-token-rotation-with-family-reuse-detection.md).

Every password-setting path — registration and password reset — runs the same
policy (`backend.auth.password_policy.validate_password_strength`): a
length-tier minimum (`AUTH_PASSWORD_STRENGTH`, default `medium` / 12 chars),
a `AUTH_PASSWORD_MAX_LENGTH` ceiling, and a k-anonymity check against Have I
Been Pwned that fails open, so a HIBP outage never blocks a password change.
Each failure is a `422`.

`POST /auth/forgot-password` always answers `204` with an empty body —
identical status, body, and (within `AUTH_FORGOT_PASSWORD_RESPONSE_FLOOR`)
timing whether or not the address has a verified account, so it can't be used
to enumerate users. Only a verified account gets a `password_reset_token`
emailed (via the same outbox as verification, `EmailKind.PASSWORD_RESET`).
`POST /auth/reset-password` consumes the token, applies the password policy,
re-hashes the password, revokes every refresh-token session for that user,
and burns any other outstanding reset token. An invalid or expired token is a
`400`.

```mermaid
sequenceDiagram
    participant Client
    participant Frontend
    participant API
    participant DB

    Client->>API: POST /auth/register
    API->>DB: create user, verification token, outbox entry
    API-->>Client: 201, queues verification email

    Note over Client,API: user clicks the emailed confirm-email link
    Client->>Frontend: redirects to /verify-email-confirm?token=...
    Frontend->>API: POST /auth/confirm-email
    API->>DB: mark_email_verified
    API-->>Frontend: confirmed

    Client->>API: POST /auth/login
    API->>DB: check credentials + email_verified_at
    API-->>Client: 200, sets access/refresh cookies, returns token pair

    Client->>API: POST /auth/refresh (old refresh token)
    API->>DB: mark old token used, create new token (same family_id)
    API-->>Client: 200, new token pair

    Note over Client,API: old refresh token reused (e.g. stolen + replayed)
    Client->>API: POST /auth/refresh (same old token again)
    API->>DB: revoke_family(family_id)
    API-->>Client: 401 — whole family revoked

    Client->>API: POST /auth/forgot-password
    API->>DB: if verified account, create reset token + outbox entry
    API-->>Client: 204 (identical for unknown addresses)

    Note over Client,API: user clicks the emailed reset link
    Client->>API: POST /auth/reset-password (token, new password)
    API->>DB: burn token, set password_hash, revoke all sessions
    API-->>Client: 204
```

## Email delivery

Registration and resending verification don't call the email provider
directly — they write a row to `email_outbox` in the same DB transaction as
the triggering action, with an `EmailKind` to select the template, then
queue a Celery task to dispatch it. A periodic sweep re-queues anything left
stuck `PENDING`. This keeps the email durable even if Celery/Redis is
unavailable at the moment of the request. See [ADR 3](decisions/0003-durable-email-outbox-before-dispatch.md).

```mermaid
flowchart LR
    A[POST /auth/register] -->|same DB transaction| B[(email_outbox: PENDING)]
    A -->|.delay| C[Celery: dispatch_email]
    C -->|success| D[(email_outbox: SENT)]
    C -->|failure, attempts < max| E[Celery retry with backoff]
    E --> C
    C -->|failure, attempts >= max| F[(email_outbox: DEAD)]
    G[Celery beat: sweep_pending_emails] -->|entries stale past threshold| B
    G --> C
```

## Decisions

See [architecture decisions](decisions/index.md) for the reasoning behind
these choices.
