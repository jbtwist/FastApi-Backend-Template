# Backend Template

A ready-made backend for apps that need user accounts, so you don't have to build
sign-up and login from scratch again.

It's written in [FastAPI](https://fastapi.tiangolo.com/) (Python) and built to be
**elastic**. The server doesn't keep anything in its own memory between requests:
everything it needs to remember lives in a shared database (Postgres) and a shared cache
(Redis). So when more people show up, you run more copies of the server behind a load
balancer, and they all work as one. The code puts no limit on how many users you can
serve; that's up to how many machines you give it.

## What you get

- **Accounts:** sign up, confirm your email, log in, log out, forgot and reset password.
- **Sign in with Google and Apple**, linked safely to existing accounts.
- **Sessions that renew themselves**, with detection of stolen login tokens.
- **Rate limiting**, so nobody can hammer the login form.
- **Email that doesn't get lost:** if the mail service is down, messages wait and go out later.
- **Audit logs** of who did what and when.

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
