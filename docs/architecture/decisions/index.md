# Architecture decisions

- [1. Refresh token rotation with family-based reuse detection](0001-refresh-token-rotation-with-family-reuse-detection.md)
- [2. Deliver tokens via both httponly cookies and the response body](0002-dual-cookie-and-body-token-delivery.md)
- [3. Durable email outbox before Celery dispatch](0003-durable-email-outbox-before-dispatch.md)
- [4. Email verification links point to frontend](0004-email-verification-via-frontend.md)
- [5. The frontend owns all auth error copy](0005-frontend-owns-auth-error-copy.md)
- [6. Harden npm installs instead of adopting pnpm](0006-harden-npm-installs-over-pnpm.md)
- [7. Structured logs to stdout, with audit events on their own logger](0007-structured-logs-to-stdout-with-an-audit-stream.md)

Add one per significant decision (library choice, pattern, data store) as `NNNN-short-title.md` in this folder, with the same sections as the records above: Date, Status, Context, Decision, Alternatives considered, Consequences.
