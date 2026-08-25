# Getting started: register, verify, and log in

This walks through the full account flow against a locally running backend:
register, confirm the email, log in, call an authenticated endpoint, and
refresh the session.

## Prerequisites

Start the backend and its dependencies (Postgres, Redis, the Celery worker
and beat scheduler, and an SMTP catcher such as [Mailpit](https://mailpit.axllent.org/)
on `localhost:1025` — see `backend/.env.example` for the expected connection
settings):

```bash
cd backend
uv sync
uv run uvicorn backend.main:app --reload
```

<!-- TODO: confirm the exact commands to start the Celery worker/beat and Postgres/Redis once there's a settled way to run them (no docker-compose or Procfile yet). -->

## 1. Register

```bash
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "password": "correct-horse-battery"}'
```

Returns the new user with `"email_verified": false`. This also queues a
verification email — check your SMTP catcher's inbox for it.

## 2. Confirm your email

Open the confirmation link from the email (`GET /auth/confirm-email?token=...`)
in a browser, or extract the `token` query parameter and call it directly:

```bash
curl "http://localhost:8000/auth/confirm-email?token=<token-from-the-email>"
```

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
