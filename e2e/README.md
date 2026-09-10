# End-to-end tests

Playwright driving the Expo web client in a real browser against a real
FastAPI + Postgres stack. It covers what the jest and pytest suites cannot:
CORS on error responses, httponly cookie scoping, refresh-token rotation across
an actual request, and the emailed verification and reset links.

It is a thin layer on purpose. Feature-by-feature behaviour belongs in the
frontend's `@testing-library/react-native` specs, which are faster, hermetic,
and — unlike a browser — can cover the native session path.

## Running it

```bash
npm install            # first time
npx playwright install chromium

npm test               # all specs
npm test -- --headed   # watch it drive the browser
npm test -- --ui       # pick and re-run specs interactively
npm run report         # open the last HTML report
```

Playwright starts both servers itself. All you need running is Postgres.

## What it starts

| Piece | Where | Notes |
| --- | --- | --- |
| Postgres database `todoapp_e2e` | your local server | created on demand by `scripts/ensure-db.mjs` |
| API | `localhost:8100` | `scripts/start-backend.sh`: migrate, then uvicorn |
| Web client | `localhost:8082` | `expo start --web`, built with `EXPO_PUBLIC_API_URL` |

Ports 8100/8082 are deliberately *not* the dev ports. Playwright reuses an
already-listening server, so sharing 8000/8081 would let it silently adopt your
dev backend and run the whole suite against your dev database.

No Redis, no Celery worker and no SMTP server are needed — see `.env.e2e`.

If your Postgres does not accept the default connection, point the suite
somewhere else without editing the file:

```bash
E2E_DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/todoapp_e2e npm test
```

## How it reads verification and reset tokens

Those tokens only ever reach a user by email. `email_outbox` holds the
plaintext copy — that row *is* the delivery payload, while the token tables
store only its hash — so `fixtures/db.ts` reads it straight from Postgres.
That is why no mail server is in the loop.

## Conventions

- Every test mints a unique address, so accounts never collide and there is no
  teardown. Nothing truncates tables between tests.
- Selectors go through the accessible name (`getByLabel`, `getByRole`) wherever
  there is one, so a test also fails when an affordance regresses.
- Assertions name English copy; the browser locale is pinned to `en-US` in
  `playwright.config.ts`.
- Nothing in `backend/` or `frontend/` is modified to make this run.
  Configuration reaches both through the environment only.

## What it has already caught

Stolen-refresh-token detection revoked nothing. `rotate_refresh_token` did call
`revoke_family`, but the endpoint raised to answer 401 and `get_db` wraps each
request in `session.begin()` — so the rollback took the revocation with it, and
the thief's successor token kept working. Reuse is now reported as a return
value and the endpoint returns its 401 instead of raising.

The pytest suite could not see it: its fake repositories have no transaction to
roll back. `specs/silent-refresh.spec.ts` covers it from the browser, and
`backend/tests/auth/test_reuse_revocation.py` now covers it against real
Postgres.
