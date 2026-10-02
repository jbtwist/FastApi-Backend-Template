# Getting started: register, verify, and log in with the API

This walks through the full account flow against a locally running backend:
register, confirm the email, log in, call an authenticated endpoint, and
refresh the session. Everything here is `curl` against the API.

To walk the same flow through the Expo web client instead, with screenshots of
each screen, see [Create an account in the web client](web-client.md).

## Prerequisites

### Have these running

Five pieces sit behind the API. The first three you install and start yourself;
the two Celery processes are started from `backend/` further down.

| | Where the defaults expect it | What needs it |
| --- | --- | --- |
| **Postgres** 14 or newer | `localhost:5432` | everything — the API will not start without it |
| **Redis** | `localhost:6379` | the per-route rate limiter on db `0`, the Celery broker on db `1` |
| An **SMTP catcher**, e.g. [Mailpit](https://mailpit.axllent.org/) | `localhost:1025` | where the worker delivers, so you can read the link |
| **Celery worker** | `backend/` | the only thing that sends a queued email — without it the outbox row just sits `PENDING` |
| **Celery beat** | `backend/` | re-queues rows whose dispatch was lost; a safety net, not the delivery path |

Registering writes a row in the outbox and queues `dispatch_email`. No email is
sent until a Celery worker is up. Beat
runs `sweep_pending_emails`, which re-dispatches rows never attempted for
`EMAIL_SWEEP_STALE_AFTER_SECONDS`, or idle between retries for
`EMAIL_SWEEP_RETRYING_STALE_AFTER_SECONDS` — so mail still sends without beat, it just
stops recovering from a lost enqueue. See
[the outbox decision](../architecture/decisions/0003-durable-email-outbox-before-dispatch.md).


### Configure

The three settings classes each read `backend/.env` at import, so the file has
to exist before anything starts:

```bash
cp .env.example .env
uv sync
```

`.env.example` matches every default on this page. Five settings have no
fallback and must be present or the process fails to import:

| Setting | Why |
| --- | --- |
| `DATABASE_URL` | the async Postgres DSN (`postgresql+asyncpg://…`) |
| `JWT_SECRET` | signs access tokens; any random string locally |
| `CELERY_BROKER_URL` | where `dispatch_email` is queued |
| `CELERY_RESULT_BACKEND` | where Celery stores task results |
| `FROM_EMAIL` | sender address on outgoing mail |

Two more have defaults that are wrong for a local run, and `.env.example`
already overrides both:

- `COOKIE_SECURE` defaults to `true`, which makes a browser discard the auth
  cookies over plain `http`. Locally it has to be `false`. That override is for
  local `http` only — any deployment served over `https` keeps the `true`
  default, or the session cookies travel in plaintext.
- `REDIS_URL` is read by the rate-limiting library's own settings, not by
  `backend.config.Settings` — it is absent from the backend's config classes
  by design, so don't go looking for it there.

### Create the database and migrate

Alembic connects to `DATABASE_URL` but will not create the database itself:

```bash
createdb backend_template
uv run alembic upgrade head
```

### Start the processes

Three terminals, all in `backend/`:

```bash
uv run uvicorn backend.main:app --reload                        # the API, on :8000
uv run celery -A backend.mail.celery_app worker --loglevel INFO # sends queued email
uv run celery -A backend.mail.celery_app beat                   # re-queues email stuck PENDING
```

Confirm the API is up before going on:

```bash
curl http://localhost:8000/health   # {"status":"ok"}
```

### Running with less

Only Postgres is truly required. Two things are safe to drop while you're
finding your feet:

- **No Redis.** Set `RATE_LIMIT_ENABLED=false`, which removes the limiter's
  dependency rather than skipping it, so no request path resolves a Redis
  client. Queuing an email is already best-effort — a failed `.delay` is logged
  and swallowed, the outbox row having been committed first.
- **No worker, no beat, no SMTP catcher.** Nothing sends the email, but the row
  is still written, and it holds the token in the clear (the token tables store
  only its hash). Read it straight out of Postgres instead of an inbox:

  ```bash
  psql backend_template -c "SELECT token FROM email_outbox \
    WHERE email = 'you@example.com' AND kind = 'verification' \
    ORDER BY created_at DESC LIMIT 1;"
  ```

One default reaches the network: `PASSWORD_CHECK_PWNED=true` calls
`api.pwnedpasswords.com` on every register and password reset. It fails open,
so being offline costs you the breach check but nothing else. Set it to `false`
to skip the call.

## 1. Register

```bash
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "password": "correct-horse-battery"}'
```

Returns `204 No Content` with an empty body, and queues a verification email —
check your SMTP catcher's inbox for it.

The response is deliberately identical whether or not the address was already
registered, so it can't be used to discover who has an account. That means a
`204` is not confirmation that a new user was created.

## 2. Confirm your email

The emailed link points at the frontend, not the API
(`{FRONTEND_BASE_URL}/verify-email-confirm?token=...` — see
[the verification-link decision](../architecture/decisions/0004-email-verification-via-frontend.md)).
Opening it in the running Expo app confirms the address for you.

To do it from the terminal instead, take the `token` query parameter out of the
link and post it:

```bash
curl -X POST http://localhost:8000/auth/confirm-email \
  -H "Content-Type: application/json" \
  -d '{"token": "<token-from-the-email>"}'
```

Returns `204 No Content`. An expired or already-used token is a `400`.

## 3. Log in

```bash
curl -i -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "password": "correct-horse-battery"}'
```

Login fails with `403` if the email isn't confirmed yet. On success, the
response sets `access_token`/`refresh_token` cookies and also returns both
tokens in the body — use whichever fits your client (see
[the dual-delivery decision](../architecture/decisions/0002-dual-cookie-and-body-token-delivery.md)).

## 4. Call an authenticated endpoint

Using the cookies `curl -i` just received (`-b`/`-c` to persist them), or the
`access_token` from the body as a bearer token:

```bash
curl http://localhost:8000/auth/me \
  -H "Authorization: Bearer <access_token>"
```

## 5. Refresh the session

Access tokens expire after 15 minutes. Exchange the refresh token for a new
pair before then:

```bash
curl -X POST http://localhost:8000/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token": "<refresh_token>"}'
```

The old refresh token stops working immediately — save the new one from the
response. Presenting the old one again is treated as token theft and revokes
the whole session (see
[the reuse-detection decision](../architecture/decisions/0001-refresh-token-rotation-with-family-reuse-detection.md)).
