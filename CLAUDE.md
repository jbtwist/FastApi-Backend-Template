# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

Two independent apps in one tree that meet over a JSON auth API:

- **`backend/`** — a FastAPI app (`backend.main:app`). Designed to scale **horizontally**: keep it stateless, push all shared state to Postgres / Redis.
- **`frontend/`** — an Expo (React Native) app, **SDK 57**. First and foremost a *reusable public JWT-auth template*; the todo/GTD product UI comes later. Not expected to scale horizontally (it's a client).
- **`docs/`** — MkDocs (Material) site, config at repo-root `mkdocs.yml`. Owned by the `docs` skill.
- **`taskify/`** — spec-driven-development workspace (specs, plans, task lists). **Gitignored, never committed.** Code and comments must not reference anything in it (see Conventions).

`GLOSSARY.md` lives at `.claude/skills/docs/GLOSSARY.md` — nowhere else.

## Commands

### Backend (run from `backend/`)

```bash
uv run pytest                              # full suite
uv run pytest tests/auth/test_service.py   # one file
uv run pytest -k "reuse_detected"          # one test by name
uv run pytest -x --tb=short                # stop on first failure

uv run ruff check --fix src                # lint
uv run ruff format src                     # format

uv run alembic upgrade head                             # apply migrations
uv run alembic revision --autogenerate -m "add x table" # new migration (dated filename)

uv run uvicorn backend.main:app --reload                       # dev server
uv run celery -A backend.mail.celery_app worker --loglevel INFO # email dispatch worker
uv run celery -A backend.mail.celery_app beat                   # periodic outbox sweep
```

Python 3.14, managed by `uv`. Needs Postgres and Redis running (see `backend/.env.example`). Real-database tests never touch `DATABASE_URL` itself: each run creates `<name>_test`, builds it with `alembic upgrade head`, and drops it afterwards, so the Postgres role needs `CREATEDB`.

### Frontend (run from `frontend/`)

```bash
npm ci                       # install; .npmrc blocks dep scripts + 3-day release cooldown (ADR 6)
npm test                     # jest (jest-expo preset)
npm test -- sign-in          # tests matching a pattern
npm run typecheck            # tsc for app + test tsconfigs
npm run lint                 # expo lint (eslint)
npm start | npm run ios | npm run web
```

Before writing any frontend code, consult the versioned Expo docs for SDK 57: <https://docs.expo.dev/versions/v57.0.0/>. APIs shift between SDKs.

### Docs (run from repo root, backend env)

```bash
uv run --project backend --group docs mkdocs serve         # preview
uv run --project backend --group docs mkdocs build --strict # must pass clean
```

## Backend architecture

**Domain packages under `src/backend/`** — currently `auth/` and `mail/`. Each holds `router.py` `schemas.py` `models.py` `repository.py` `service/` `dependencies.py` `config.py` `exceptions.py`. Shared/global modules sit at the top: `config.py` `database.py` `models.py` `rate_limit.py` `cors.py` `main.py`. Cross-domain imports use the explicit module (`from backend.mail.tasks import dispatch_email`), never deep paths or `*`.

**Layering.** Routes are thin (parse, call service, shape response). Business logic lives in `service/`. Persistence is behind a **`typing.Protocol`** repository interface: e.g. `UserRepository` (Protocol) + `SqlUserRepository` (real) + a fake in `tests/`. Services receive repositories as parameters — they never construct a session. Shared repo behaviour uses a generic base class (`_SqlSingleUseTokenRepository[TokenT]`), not inheritance of the Protocol.

**Database (`database.py`).** Two engines: `engine` / `SessionFactory` (pooled, `pool_pre_ping`, used by the `get_db` request dependency, which opens a transaction with `session.begin()`); and `worker_engine` / `WorkerSessionFactory` (`NullPool`, for Celery tasks — each task's `asyncio.run()` is a fresh loop and asyncpg connections are loop-bound). SQLAlchemy 2.0 async throughout. Postgres index/constraint naming convention is set on the shared `MetaData`.

**Settings are split by domain but share one flat env namespace.** `Settings` (`config.py`), `AuthConfig` (`auth/config.py`), `MailConfig` (`mail/config.py`) each read the same `.env` with **no `env_prefix`**. A field's name *is* its environment variable name, so field names must be globally unique across all three classes and self-describing on their own (`EMAIL_PROVIDER`, not `PROVIDER`).

**Auth model.** Login and refresh return an access token (JWT HS256, 15 min) and a refresh token (opaque, 30 days, single-use), delivered **both** as httponly cookies and in the response body so browser and native clients each use what fits. Refresh tokens rotate on every use; reusing a spent token revokes its whole `family_id` (stolen-token detection without logging out other sessions). Opaque tokens (refresh, email-verification, password-reset) are stored only as `sha256` hashes. Passwords are argon2. See `docs/architecture/overview.md` and the ADRs.

**Email is a durable outbox.** `register` / `resend-verification` / `forgot-password` write an `email_outbox` row in the *same DB transaction* as the triggering change, then `.delay` a Celery `dispatch_email`. A Celery-beat `sweep_pending_emails` re-queues anything stuck `PENDING`. So mail survives a Redis/Celery outage at request time.

**Rate limiting.** Always `from backend.rate_limit import rate_limit` — never import from `redis_fastapi` directly (that bypasses the `RATE_LIMIT_ENABLED` switch). When disabled the library dependency is not installed at all, so a load test needs no Redis.

## Frontend architecture

**Routing.** Expo Router, file-based, under `src/app/`. Groups: `(auth)/` (signed-out screens), `(app)/` (signed-in, with a `(tabs)/` layout). Root `app/_layout.tsx` nests providers `LocaleProvider → ColorSchemeProvider → NavigationTheme → AuthProvider` and withholds the `<Slot/>` until the auth launch probe settles. `@/` path alias → `src/`.

**Auth session.** `auth/auth-context.tsx` is a state machine (`loading → signedIn | signedOut`, plus `renewing` / `expired` labels). It delegates transport to `auth/api-client.ts`, which:
- attaches the session per platform: `Authorization: Bearer` + `expo-secure-store` on native; `credentials: 'include'` (cookies) on web — no token touched on web.
- runs a **single-flight** refresh-on-401: coalesce concurrent 401s onto one `POST /auth/refresh`, retry the original request once, else clear the local session and fire `onSessionExpired`.
- maps every failure to a typed `AuthUiError` (`auth/errors.ts`).

**The frontend never renders text the backend wrote.** Failures are classified from HTTP status + endpoint context into an `AuthUiError`, and each screen picks its own translated copy. This is what keeps error messages localized without the API having a localization layer (ADR 5).

**i18n (`src/i18n/`).** `i18n-js`, locales `en` / `es` in `locales/<code>/`. Translation keys are type-checked (`TranslationKey`). Anything that persists across renders (a field error, a banner) stores a **`Message`** (key + options as data), *not* the output of `t()`, and resolves it at render time via `resolveMessage` — so a message already on screen follows a language switch instead of freezing in the old language. Validators in `forms/validators.ts` return keys for the same reason.

**Theme (`src/theme/` + `src/constants/theme.ts`).** Light/dark palettes only. There is no "system" value — "follow the device" is the *absence* of a stored choice in AsyncStorage. Same shape as the locale preference. Neither preference reaches the backend.

**Forms.** `forms/use-form.ts` — a small hand-rolled hook (values, per-field errors, `touched`, form banner, double-submit guard). No form library.

## Testing

### Backend — TDD (`tdd` skill)

Write the tests first, then scaffold the skeleton they import — real modules in their architectural home, full signatures and type hints, docstrings, `raise NotImplementedError` bodies, complete schemas/models/exceptions, no logic. Run them, confirm they fail on an assertion or `NotImplementedError` (never an import or collection error), then **stop and wait for the go-ahead** before implementing. Prefer fixtures / fakes / stubs over mocks; mock only at the edges (I/O, time, randomness). Do **not** test endpoint functions directly — test the service/helper functions they call; keep endpoints thin. Do **not** write "429 after N requests" threshold tests — the mechanism is covered in `tests/test_rate_limit.py` and the threshold is a tuning knob; just add the decorator. If a change touches an untested module, add coverage for it in the same change.

### Frontend — BDD

Behavior-focused tests with `@testing-library/react-native`: render the screen, drive it as a user would (type, press), assert on what's visible. `jest-setup.ts` installs in-memory fakes for `expo-secure-store`, `@react-native-async-storage/async-storage`, and snapshots `fetch` per test. Route and layout tests go in `src/app/**/__tests__/` — **not** beside the route file, because expo-router treats a `*.test.tsx` next to a route as a route.

## Conventions

- **Glossary first.** Before naming any variable, function, class, Pydantic field, DB column, API field, or storage key, check `.claude/skills/docs/GLOSSARY.md` and use the canonical name exactly. If the concept is missing, add it to the glossary first, then write the code. `snake_case` in Python, `camelCase` in TS.
- **Comments: what, not why, and rarely.** No inline comments explaining rationale. Put rationale in a docstring (Python, Google style) or TSDoc (`/** */`) on the exported symbol — mkdocstrings and TSDoc publish those; inline comments are invisible. A short comment stating a non-obvious *what* is fine.
- **Docstrings are short.** Write for a reader who knows the language and this repo but was not in the conversation that produced the code, and who is skimming.
  - A function or class gets **one line**: what it does. `Args:` / `Raises:` stay when a parameter or error needs them.
  - Prose belongs in the **module docstring** — why the module exists, plus any rule for callers (`import rate_limit from here, never the library`). Say it once there and never restate it in a symbol below.
  - A symbol earns a second paragraph only for a fact the body cannot show: it fails open, it returns `False` instead of raising, the insert runs in a savepoint. Cite a source (OWASP, NIST, an RFC) when a number would otherwise look arbitrary.
  - Delete anything that narrates the code beneath it ("checks in order: too short → too long → breached") or justifies a design choice the reader isn't questioning.
  - Endpoint docstrings in `router.py` are the published OpenAPI description — trim them, but keep them useful to an API consumer.
  - Plain commas over em-dashes. Ruff's 100-char limit applies to docstring lines too.
- **No spec-driven-development references in code or comments.** `taskify/` is not committed, so `FR-036`, `SC-013`, `T022`, `contracts/auth-api.md`, `data-model.md`, "ADR 5" etc. must not appear in `src/`. Some legacy violations exist — remove them when you touch that code.
- **No `abc.ABC` / `@abstractmethod`.** Use `typing.Protocol` for interfaces; for shared behaviour use a plain mixin with `NotImplementedError` hooks.
- **ADR bar.** An ADR needs a real either/or tradeoff with alternatives considered. A config-tunable security knob is not an ADR.
- **No animations** unless explicitly requested.
- **Keep it simple.** Don't overengineer.
- **Frontend priorities:** i18n, accessibility, a color palette that works for color-blind users, performance.
- **Backend security, every feature:** think through the rate-limit strategy, secret exposure, RNG quality, and enumeration / timing oracles (see how `register` and `forgot-password` return byte-identical `204`s with a response-time floor).
- **Migrations** are static, reversible, async-template, dated filenames (`2026-09-01_add_password_reset_token_*.py`).

## Automation

- `git commit` and `gh pr create` are pre-approved in `.claude/settings.json`.
- `.github/workflows/docs-sync.yml`: after any PR merges to `main`, a Gemini job runs the `docs` skill and opens a follow-up `docs/update-after-<PR#>` PR if the change is user- or developer-observable.
- Use the `docs` skill for anything under `docs/`, the `mkdocs.yml` nav, the glossary, or keeping docstrings in sync.
