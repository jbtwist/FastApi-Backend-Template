# Backend Template

A ready-made backend for apps that need user accounts, so you don't have to build
sign-up and login from scratch again. It's written in
[FastAPI](https://fastapi.tiangolo.com/) (Python), and comes with a demo app to click
through it.

## What you get

- **Accounts:** sign up, confirm your email, log in, log out, forgot and reset password.
- **Sign in with Google and Apple**, linked safely to existing accounts.
- **Sessions that renew themselves**, with detection of stolen login tokens.
- **Rate limiting** that slows down password guessing and other abuse.
- **Email that doesn't get lost:** if the mail service is down, messages wait and go out later.
- **Audit logs** of who did what and when.

## Try it

You need [Docker](https://docs.docker.com/get-docker/). From the root of the project:

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml \
  --env-file deploy/local.env up --build
```

The API answers on <http://localhost:8000> (interactive docs at `/docs`), and every email
it sends lands in Mailpit at <http://localhost:8025>. To work on the code itself you'll
also want [uv](https://docs.astral.sh/uv/) for the backend and Node.js for the frontend;
[Getting started](docs/getting-started/index.md) walks through both.

## How it runs

```mermaid
flowchart LR
    Client["Client<br/>(phone app / browser)"] --> LB[Load balancer]
    CDN["Static host / CDN<br/>(web build)"] -.serves.-> Client
    LB --> A[Backend A] & B[Backend B] & C[Backend C]

    A & B & C --> PG[(Postgres)]
    A & B & C --> R[("Redis<br/>rate limits + task queue")]
    A & B & C -.-> Ext["Google / Apple sign-in<br/>Have I Been Pwned"]

    Beat["Beat × 1"] -->|sweep every 60 s| R
    R -->|tasks| W["Worker × N"]
    W --> PG
    W --> Mail[Email provider]

    M["Migrate<br/>(once per deploy)"] --> PG
```

All of it is one Docker image started with different commands:

- **Backend:** the API. Run as many copies as you need behind the load balancer.
- **Worker:** sends the emails. The backend never calls it directly: it saves the email
  in Postgres and leaves a task in Redis, and a worker picks it up. If every worker is
  down, the emails wait.
- **Beat:** a timer that, every minute, asks a worker to resend any email that got stuck.
  Run exactly one.
- **Migrate:** updates the database tables, once per deploy, before the new backends start.

Postgres holds all the data. Redis isn't a cache: it counts requests for rate limiting and
carries tasks to the workers. In production, use managed versions of both, plus your
hosting's load balancer. Any copy of the backend can answer any request, so running two
or twenty takes no code changes.

## Does a login API need to scale?

Rarely, and this template doesn't pretend it does. It's meant as a starting point: you
add your own features next to `auth/` and `mail/`, and they inherit the same stateless
design. That's where running more copies pays off. If all you need is login, a hosted
service (Keycloak, Auth0, Cognito...) may suit you better. When a second copy is worth it,
and what to scale in which order, is in [Scaling](docs/architecture/overview.md#scaling).

## A frontend to try it with

The `frontend/` folder holds a basic app built with [Expo](https://expo.dev/). It runs in
your web browser, so you can click through every screen (sign up, log in, reset your
password) and see the backend working with a real interface instead of raw requests.

It's a template too: every sign-in screen is already built, translated into English and
Spanish, and has light and dark themes. Keep it and build your app on top, or, if you
only want the backend, **delete the `frontend/` folder**. The backend doesn't depend on it.
(The `e2e/` folder tests the two together, so delete it along with the frontend.)

## How it was built

This project was built with AI agents doing most of the typing and a human deciding what
gets in. Each feature went through the same steps:

1. **Plan.** The work is broken into tasks with [Spec Kit](https://github.com/github/spec-kit),
   a spec-driven development framework. Spec Kit and its files are not included in this repo.
2. **Tests first.** One agent writes only the tests for the task, following the project's
   test architecture, and then stops.
3. **Human review of the tests.** I read and approve every test before any real code is
   written. The tests are the contract: if they're right, the code that passes them is too.
4. **Implementation.** A second agent writes the feature. It gets nothing but the task and
   the tests it has to make pass.
5. **Code review.** A third agent reviews the pull request. I decide which of its findings
   are worth tackling, then review the code a second time myself.
6. **Docs.** After merging, a GitHub Action asks an AI model to update the documentation
   and the glossary of terms (the shared vocabulary of the project, in the spirit of
   domain-driven design).
7. **See it working.** Another agent writes end-to-end tests with
   [Playwright](https://playwright.dev/), which drives a real browser, so I can watch the
   feature work with my own eyes.

A note on step 6: the Action uses a free-tier model and the results are poor. It's there to
show that keeping docs up to date *can* be automated. Updating the docs by hand is still
recommended.

## Claude skills included

The project ships the [Claude Code](https://claude.com/claude-code) skills used to build
it, in `.claude/skills/`. Use them as they are or change them however you like.

- **`tdd`**: writes the tests before any code. It also creates the empty files those tests
  need, checks that the tests fail for the right reason, and then stops so a human can
  review them.
- **`docs`**: keeps the documentation site and the glossary in step with the code:
  guides, architecture decisions, diagrams, and an API reference generated from the code.

`CLAUDE.md`, at the root, holds the project's conventions so every agent works the same way.

## Learn more

How it works, how to run it, and why it's built this way are all in the documentation, in
the `docs/` folder. To read it as a website, run this from the root of the project:

```bash
uv run --project backend --group docs mkdocs serve
```

Good places to start:

- [Getting started](docs/getting-started/index.md): run the backend and make your first account.
- [Try it in the web client](docs/getting-started/web-client.md): the same, through the frontend.
- [Architecture overview](docs/architecture/overview.md): how the pieces fit together.
