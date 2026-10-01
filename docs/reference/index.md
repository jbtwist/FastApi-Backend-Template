# API reference

Auto-generated from docstrings — do not edit by hand.

For the HTTP endpoints, read the OpenAPI spec the running API serves itself, at
`/docs` (Swagger UI) or `/redoc`. It carries every request and response schema
and will call the endpoints for you, which no generated page here can. The pages
below document what that spec has no room for: the service layer behind the
endpoints, the security primitives, the password policy, and the email outbox —
none of which has an HTTP surface.

- [Auth (Backend)](auth.md) — registration, login, token rotation, email verification, password reset.
- [Password Policy](password_policy.md) — length rules and the Have I Been Pwned breach check.
- [Mail](mail.md) — the email outbox and its Celery dispatch.
- [Logging](log.md) — stdout configuration, formatters, and the `audit_event` API.

Backend only: mkdocstrings is configured with the Python handler, so there is no
generated reference for the Expo app. Frontend modules document themselves in
TSDoc, which editors surface at the call site — `src/auth/errors.ts` carries the
auth-failure classification — and the guides cover the parts worth explaining in
prose: [adding a language](../guides/add-a-language.md) and
[theming](../guides/theming.md).
