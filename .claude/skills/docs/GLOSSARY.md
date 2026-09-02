# Domain Glossary

Single source of truth for naming. Before naming any variable, function, class, or field, check here first. If the concept exists, use the exact term listed. If it doesn't exist, add it before writing code.

## Rules

- One canonical name per concept. No synonyms in code.
- Snake_case for Python variables and functions. PascalCase for classes. camelCase for TypeScript/JavaScript.
- Abbreviations only if listed here. Never invent new ones.
- If a name is already in production (DB column, API field, mobile storage key), that name wins — add it here as-is.

## How to add an entry

```
| Concept             | Canonical name     | Avoid               |
|---------------------|--------------------|---------------------|
| <plain description> | <exact code name>  | <rejected variants> |
```

---

## Glossary

| Concept | Canonical name | Avoid |
|---|---|---|
| A task the user wants to track | `task` | `todo`, `item`, `entry` |
| The user who owns data in the system | `user` | `account`, `member`, `profile` |
| A session token issued after login | `access_token` | `token`, `jwt`, `auth_token` |
| A token used to renew the access token | `refresh_token` | `renew_token`, `rt` |
| The moment a record was created | `created_at` | `created`, `creation_date`, `timestamp` |
| The moment a record was last modified | `updated_at` | `updated`, `modified_at`, `last_modified` |
| Whether a task has been completed | `is_done` | `done`, `completed`, `finished`, `is_complete` |
| The text content of a task | `title` | `name`, `description`, `text`, `content` |
| The ordering position of a task | `position` | `order`, `index`, `rank`, `sort_order` |
| A group of tasks | `list` | `collection`, `group`, `board`, `category` |
| A user's hashed password | `password_hash` | `password`, `hashed_password` |
| Group of refresh tokens from one login, used for rotation + reuse detection | `family_id` | `session_id`, `chain_id` |
| The moment a refresh token was consumed by rotation | `used_at` | `consumed_at`, `rotated_at` |
| The moment a refresh token (or its family) was invalidated early | `revoked_at` | `invalidated_at`, `disabled_at` |
| The moment a token stops being valid | `expires_at` | `expiry`, `exp_date`, `valid_until` |
| An access_token + refresh_token issued together | `token_pair` | `tokens`, `pair` |
| The auth scheme reported to bearer-token clients | `token_type` | `type`, `auth_type`, `scheme` |
| A durable row recording an email that still needs to be sent, retried independently of the request that created it | `email_outbox_entry` (table `email_outbox`) | `mail_job`, `email_queue_item`, `outbox_row` |
| Writing an outbox row without contacting the provider (generic mail-layer primitive) | `enqueue_email` | `queue_email`, `add_to_outbox` |
| Auth-domain action: mint a verification token and put its email on the outbox | `queue_verification_email` | `send_verification_email` (misleading — doesn't send) |
| The step that actually calls the email provider for one outbox entry | `dispatch_verification_email` | `send_email`, `deliver_email` |
| The lifecycle states of an outbox entry | `EmailOutboxStatus`: `pending`, `sent`, `dead` | `queued`, `failed`, `completed` |
| Count of failed dispatch attempts on an outbox entry | `attempts` | `retry_count`, `tries` |
| The periodic job that re-dispatches outbox entries stuck in `pending` | `sweep` (e.g. `sweep_pending_emails`) | `relay`, `reaper`, `poller` |
| The moment an outbox entry was successfully sent | `sent_at` | `delivered_at` |
| The moment an outbox entry was permanently given up on | `dead_at` | `failed_at`, `abandoned_at` |
| The moment of the most recent dispatch attempt on an outbox entry | `last_attempted_at` | `last_tried_at`, `retried_at` |
| The stored, hashed form of a raw refresh or email-verification token (never store the raw token) | `token_hash` | `hashed_token`, `token_digest` |
| A short-lived token proving ownership of an email address, sent as a link | `email_verification_token` | `verify_token`, `confirmation_token` |
| The moment a user's email address was confirmed; `NULL` means unverified | `email_verified_at` | `verified_at`, `email_confirmed_at` |
| The minimum length tier for a password | `PasswordStrength` | `strength`, `level`, `tier` |
| The breach-check status of a password | `PASSWORD_CHECK_PWNED` | `check_breaches`, `pwned_check` |
| The maximum length allowed for a password | `PASSWORD_MAX_LENGTH` | `max_length` |
| Auth-domain action: mint a password-reset token and put its email on the outbox | `request_password_reset` | `send_password_reset_email` (misleading — doesn't send) |

