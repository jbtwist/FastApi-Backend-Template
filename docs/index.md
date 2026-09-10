# todoapp

A starting point for React Native apps that need accounts, so you don't write
authentication again.

Register, email confirmation, login, logout and password reset are built and
tested, on both sides of the wire: a FastAPI backend and an Expo client that
talks to it. Clone it, point it at your database, and start building the part
of your app that isn't auth.

## What you get

| | |
| --- | --- |
| **Accounts** | Register, confirm email, log in, log out, forgot and reset password |
| **Sessions** | 15-minute JWT access tokens, single-use refresh tokens that rotate on every use, with stolen-token detection |
| **Delivery** | Tokens as httponly cookies *and* in the response body, so browser and native clients each use what suits them |
| **Passwords** | argon2 hashing, a configurable length floor, and an optional check against known breach corpora |
| **Email** | An outbox that survives your mail service being down |
| **Rate limiting** | Per-route limits, with one switch to turn the whole thing off |
| **UI** | Every auth screen built, translated, themed, and accessible |

### Sessions that look after themselves

Login returns a short-lived access token and a long-lived refresh token. The
client renews in the background: when a request comes back the invalidated token 
generates a `401`, it's refreshed and retried, and the user notices nothing. 
Concurrent failures collapse onto a single refresh rather than stampeding.

Refresh tokens are single-use and rotate. Presenting one that has already been
spent means two parties hold the same chain, so the whole family is revoked —
that signs out the thief without touching the user's other devices. See
[the rotation decision](architecture/decisions/0001-refresh-token-rotation-with-family-reuse-detection.md).

### Email that survives an outage

Registering writes the outbox row in the **same database transaction** as the
user, then asks Celery to send it. If your SMTP provider is down, or Redis is,
or the worker is mid-deploy, the row is still there and a periodic sweep
re-queues it. Nobody registers into a void because the mail service picked that
second to fall over. See
[the outbox decision](architecture/decisions/0003-durable-email-outbox-before-dispatch.md).

### A UI you can ship or replace

Every screen is built: register, verify, sign in, forgot password, reset
password. They ship with `en` and `es`, a light and a dark palette, and a
language and theme switcher already wired in. Translation keys are
type-checked, so a missing one fails the build rather than rendering a blank.

Error messages are the client's own text chosen from the HTTP status, never
strings the API sent — that is what keeps them translated without the API
needing a localisation layer. See
[the error-copy decision](architecture/decisions/0005-frontend-owns-auth-error-copy.md).

### Limits you can turn off

Every auth route carries a rate limit. Setting `RATE_LIMIT_ENABLED=false`
removes the dependency entirely rather than skipping it, so a load test needs
no Redis at all and measures your code instead of the limiter.

## The stack

- **Backend** — FastAPI, SQLAlchemy 2.0 async, Postgres, Alembic, Celery, Redis. Python 3.14, managed by `uv`.
- **Frontend** — Expo SDK 57 with Expo Router, running on iOS, Android and the web from one codebase.

## Run it

Backend, from `backend/`. Postgres is required. Redis backs both the rate
limiter and the Celery queue, so you can skip it while you're finding your feet
— set `RATE_LIMIT_ENABLED=false` and accept that queued emails sit in the
outbox until a worker picks them up:

```bash
uv sync
cp .env.example .env
createdb todoapp
uv run alembic upgrade head
uv run uvicorn backend.main:app --reload
```

Frontend, from `frontend/`:

```bash
npm ci
npm run web
```

`npm ci` here runs no dependency install scripts and honours a three-day release
cooldown, both set in `frontend/.npmrc`.

To actually receive the verification and reset emails, run an SMTP catcher such
as [Mailpit](https://mailpit.axllent.org/) on `localhost:1025` plus the Celery
worker and beat scheduler — see
[the API walkthrough](getting-started/index.md) for the full sequence.

## What you'll change first

The user model is deliberately almost empty — `id`, `email`, `password_hash`,
`email_verified_at`, and timestamps, in `backend/src/backend/auth/models.py`.
There is no profile, no display name, no roles. Add what your product needs and
generate a migration; nothing in the auth flow assumes more than what is there.

Third-party sign-in is scaffolded but **not implemented**: the screens render
Google and Apple buttons driven by `authConfig.providers`, and they stay inert
until `oauthEnabled` is turned on. There are no provider endpoints in the
backend yet, so wiring one up is your work.

## Where next

- [Getting started with the API](getting-started/index.md) — the account flow end to end, in `curl`.
- [Create an account in the web client](getting-started/web-client.md) — the same flow through the UI, with screenshots.
- [Guides](guides/index.md) — add a language, change the theme, use the auth components, handle deep links.
- [API reference](reference/index.md) — generated from the backend's docstrings.
- [Architecture](architecture/overview.md) — how it fits together, and the decisions behind it.
