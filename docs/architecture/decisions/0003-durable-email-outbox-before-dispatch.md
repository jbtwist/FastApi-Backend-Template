# 3. Durable email outbox before Celery dispatch

Date: 2026-08-25

## Status

Accepted

## Context

Verification emails are triggered from `/auth/register` and
`/auth/resend-verification`. Handing an email straight to Celery
(`.delay()` with no persisted record) means that if Celery/Redis is down, or
the process dies between enqueueing and the broker accepting the message, the
email is silently never sent and there's no record it was ever supposed to
go out.

## Decision

Registering (or resending) a verification email first writes a row to
`email_outbox` (`backend.mail.service.enqueue_email`), in the same DB
transaction as the action that triggered it. A Celery task
(`backend.mail.tasks.dispatch_verification_email`) then does the actual send
and updates the row's status. A periodic sweep
(`backend.mail.tasks.sweep_pending_emails`) re-dispatches any entry still
`PENDING` past `SWEEP_STALE_AFTER_SECONDS`, catching cases where the initial
dispatch was never queued or got lost.

This gives a durable, queryable record of every email the app has ever
attempted to send, and a recovery path that doesn't depend on the triggering
request having succeeded in reaching Celery.

## Alternatives considered

- **Straight to Celery, no DB row** — simplest, but not durable: an outage at
  enqueue time loses the email with no trace.
- **A dedicated queue (e.g. SQS) instead of Postgres** — considered, but
  rejected for now to avoid adding another piece of infrastructure this
  early; the existing Postgres transaction already gives durability for free.

## Consequences

- Every outbound email type needs an outbox entry, not just a Celery call —
  more boilerplate per email type than a bare task.
- `sweep_pending_emails` runs on a fixed interval (`SWEEP_INTERVAL_SECONDS`)
  regardless of load, which is simple but not event-driven — recovery from a
  lost dispatch is bounded by the sweep interval, not immediate.
