# API reference

Auto-generated from docstrings — do not edit by hand.

- [Auth (Backend)](auth.md) — registration, login, token rotation, email verification, password reset.
- [Password Policy](password_policy.md) — length rules and the Have I Been Pwned breach check.
- [Mail](mail.md) — the email outbox and its Celery dispatch.

Backend only: mkdocstrings is configured with the Python handler, so there is no
generated reference for the Expo app. Frontend modules document themselves in
TSDoc, which editors surface at the call site, and the guides cover the parts
worth explaining in prose — [auth error messages](../guides/auth-error-messages.md),
[adding a language](../guides/add-a-language.md), and [theming](../guides/theming.md).
