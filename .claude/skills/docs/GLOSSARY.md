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
| The user who owns data in the system | `user` | `account`, `member`, `profile` |
| A session token issued after login | `access_token` | `token`, `jwt`, `auth_token` |
| A token used to renew the access token | `refresh_token` | `renew_token`, `rt` |
| The moment a record was created | `created_at` | `created`, `creation_date`, `timestamp` |
| The moment a record was last modified | `updated_at` | `updated`, `modified_at`, `last_modified` |
| A user's hashed password | `password_hash` | `password`, `hashed_password` |
| Group of refresh tokens from one login, used for rotation + reuse detection | `family_id` | `session_id`, `chain_id` |
| The moment a refresh token was consumed by rotation | `used_at` | `consumed_at`, `rotated_at` |
| How long after a refresh token's `used_at` a repeat presentation still counts as a concurrent refresh rather than reuse | `REFRESH_TOKEN_REUSE_GRACE` | `refresh_leeway`, `reuse_window` |
| A spent refresh token presented again by a request racing the one that spent it — answered `409`, never revokes the family | `ConcurrentRefresh` | `RefreshRace`, `DuplicateRefresh` |
| The moment a refresh token (or its family) was invalidated early | `revoked_at` | `invalidated_at`, `disabled_at` |
| The moment a token stops being valid | `expires_at` | `expiry`, `exp_date`, `valid_until` |
| An access_token + refresh_token issued together | `token_pair` | `tokens`, `pair` |
| The auth scheme reported to bearer-token clients | `token_type` | `type`, `auth_type`, `scheme` |
| A durable row recording an email that still needs to be sent, retried independently of the request that created it | `email_outbox_entry` (table `email_outbox`) | `mail_job`, `email_queue_item`, `outbox_row` |
| Writing an outbox row without contacting the provider (generic mail-layer primitive) | `enqueue_email` | `queue_email`, `add_to_outbox` |
| Auth-domain action: mint a verification token and put its email on the outbox | `queue_verification_email` | `send_verification_email` (misleading — doesn't send) |
| The step that actually calls the email provider for one outbox entry, selecting template + sender by the row's `kind` | `dispatch_email` | `dispatch_verification_email`, `send_email`, `deliver_email` |
| Which transactional email an outbox row carries | `EmailKind`: `verification`, `password_reset`, `oauth_link` | `email_type`, `template_name` |
| The lifecycle states of an outbox entry | `EmailOutboxStatus`: `pending`, `sent`, `dead` | `queued`, `failed`, `completed` |
| Count of failed dispatch attempts on an outbox entry | `attempts` | `retry_count`, `tries` |
| The periodic job that re-dispatches outbox entries stuck in `pending` | `sweep` (e.g. `sweep_pending_emails`) | `relay`, `reaper`, `poller` |
| The moment an outbox entry was successfully sent | `sent_at` | `delivered_at` |
| The moment an outbox entry was permanently given up on | `dead_at` | `failed_at`, `abandoned_at` |
| The moment of the most recent dispatch attempt on an outbox entry | `last_attempted_at` | `last_tried_at`, `retried_at` |
| The stored, hashed form of a raw opaque token — refresh, email-verification, or password-reset (never store the raw token) | `token_hash` | `hashed_token`, `token_digest` |
| A short-lived token proving ownership of an email address, sent as a link | `email_verification_token` | `verify_token`, `confirmation_token` |
| The moment a user's email address was confirmed; `NULL` means unverified | `email_verified_at` | `verified_at`, `email_confirmed_at` |
| A short-lived token used to initiate a password reset, sent as a link | `password_reset_token` | `reset_token` |
| The minimum length tier for a password | `PasswordStrength` | `strength`, `level`, `tier` |
| The breach-check status of a password | `PASSWORD_CHECK_PWNED` | `check_breaches`, `pwned_check` |
| Whether rate limiting is enforced, per route and app-wide; off only for load testing | `RATE_LIMIT_ENABLED` | `disable_rate_limit`, `throttling_off`, `stress_mode` |
| Installing the rate-limit library on the app, honouring `RATE_LIMIT_ENABLED` | `enable_rate_limiting` | `setup_rate_limit`, `add_rate_limiting` |
| The maximum length allowed for a password | `PASSWORD_MAX_LENGTH` | `max_length` |
| A language code + optional country code | `Locale` | `lang_code`, `language`, `l` |
| The frontend subsystem managing translations | `i18n` | `internationalization`, `localization`, `l10n` |
| A file or object mapping keys to translations for a specific locale | `TranslationNamespace` | `lang_file`, `strings`, `messages` |
| A key identifying a string in the i18n subsystem | `TranslationKey` | `i18n_key`, `string_id` |
| The function used to look up a translation for a key | `t` | `translate`, `localize` |
| A message held as data rather than resolved text — a `TranslationKey`, or a key plus the options its placeholders need — so it can be translated at render time | `Message` | `messageKey`, `i18nMessage`, `LocalizedString` |
| A language's name written in that language, shown in the picker and never translated | endonym (`LOCALE_LABELS`) | `languageName`, `displayName` |
| Which of the two palettes is active | `ColorScheme`: `light`, `dark` | `theme`, `mode`, `appearance` |
| The user's explicitly stored palette choice; absent means follow the device | `preference` (`COLOR_SCHEME_STORAGE_KEY`) | `themeOverride`, `forcedScheme` |
| The palette actually on screen — the preference if set, else the device's | `useActiveColorScheme` | `currentTheme`, `resolvedScheme` |
| A backend `/auth` failure classified into the outcomes screens render, carrying no server text | `AuthUiError` | `ApiError`, `authError`, `ErrorKind` |
| The frontend layer responsible for transport, error mapping, and automatic token refresh/retry logic | `ApiClient` | `api_client`, `authClient`, `auth-client`, `transport`, `network` |
| The state machine managing auth session status (signedOut, signedIn, etc.) | `auth-context` | `auth_context` |
| Store for email/timestamp of the last verification email, used to throttle resends | `PendingVerification` | `pending_verification` |
| Whether two email addresses name the same account, ignoring case and surrounding whitespace as the backend does | `isSameEmail` | `emailsMatch`, `compareEmails` |
| Middleware that answers an unhandled exception with a 500 from inside CORS, so the error still carries CORS headers | `ServerErrorAsResponse` | `ErrorMiddleware`, `CatchAllMiddleware` |
| The minimum time an enumeration-safe endpoint will take to respond, regardless of the outcome | `REGISTER_RESPONSE_FLOOR` | `response_floor`, `min_response_time` |
| The minimum time an enumeration-safe endpoint will take to respond, regardless of the outcome; one setting per endpoint | `REGISTER_RESPONSE_FLOOR`, `FORGOT_PASSWORD_RESPONSE_FLOOR` | `response_floor`, `min_response_time` |
| Padding a block of work so it takes at least a given time, whatever its outcome — how an endpoint enforces its response floor | `minimum_duration` | `response_floor`, `add_response_floor`, `minimum_time` |
| A link between a `user` and one account at a third-party sign-in provider — a credential of the `user`, never a second kind of user | `oauth_identity` (table `oauth_identity`) | `social_account`, `federated_identity`, `oauth_user` |
| A provider's stable identifier for a person — never an email address | `provider_subject` | `sub`, `provider_id`, `external_id`, `oauth_sub` |
| Which third-party sign-in provider issued an identity; also the name of its adapter module under `auth/oauth/providers/` | `provider` (`google`, `apple`) | `issuer`, `idp`, `source` |
| The email address a provider supplied when a link was made; contact data only, never used to sign in to an existing `user` | `email_at_link` | `provider_email`, `external_email` |
| Whether the provider supplied a relay address in place of the person's own | `is_private_relay` | `is_proxy_email`, `hidden_email`, `is_private_email` |
| The moment a provider link was last used to sign in | `last_authenticated_at` | `last_login_at`, `last_used_at` |
| A signed statement from a provider about who the user is, accepted only once, at the sign-in exchange | `provider_assertion` | `id_token`, `provider_jwt`, `credential` |
| The normalised result of verifying a `provider_assertion` | `ProviderIdentity` | `OAuthUserInfo`, `Claims`, `Profile` |
| The per-provider adapter implementing the sign-in contract | `OAuthProvider` (Protocol) | `OAuthStrategy`, `Backend`, `Handler`, `Client` |
| The single-use anti-forgery value binding one sign-in attempt's browser round-trip | `state` | `csrf_token`; never `nonce`, a different value |
| The single-use replay guard the provider echoes inside a `provider_assertion` | `nonce` | `challenge`; never `state`, a different value |
| Unsigned details a provider posts back with the authorization code on the first sign-in, such as Apple's `user` form field; read only for a `display_name` | `user_details` | `profile`, `user_info`, `user_blob` |
| Attaching a provider identity to an existing `user` | `link_identity` | `connect`, `merge`, `associate` |
| Which OAuth providers a deployment offers: comma-separated adapter names; empty means password sign-in only | `OAUTH_ENABLED_PROVIDERS` | `OAUTH_PROVIDERS`, `ENABLED_PROVIDERS` |
| How long a sign-in attempt's `state` and `nonce` stay valid | `OAUTH_STATE_TTL` | `STATE_TTL`, `OAUTH_STATE_EXPIRY` |
| Google OAuth client IDs, one per platform; each is an accepted audience | `GOOGLE_CLIENT_ID_WEB`, `GOOGLE_CLIENT_ID_IOS`, `GOOGLE_CLIENT_ID_ANDROID` | `GOOGLE_CLIENT_ID`, `GOOGLE_WEB_CLIENT_ID` |
| Google's static client secret, used by the web redirect flow only | `GOOGLE_CLIENT_SECRET` | `GOOGLE_SECRET` |
| Apple developer identifiers: the team (issuer of the generated client secret), the Services ID (web audience), the bundle ID (native audience) and the `.p8` key's ID | `APPLE_TEAM_ID`, `APPLE_SERVICES_ID`, `APPLE_BUNDLE_ID`, `APPLE_KEY_ID` | `APPLE_CLIENT_ID`, `APPLE_APP_ID` |
| The contents of Apple's `.p8` signing key; never logged or echoed | `APPLE_PRIVATE_KEY` | `APPLE_KEY`, `APPLE_P8` |
| The cookie binding a browser to its sign-in attempt, separate from the session cookies | `oauth_state` | `state_cookie`, `oauth_csrf` |
| The Redis key holding one sign-in attempt until it is consumed | `oauth:state:{state}` | `oauth_state:{state}`, `oauth:{state}` |
| Public base URL of this API; what its own callback URLs are built from | `API_BASE_URL` | `BACKEND_URL`, `SERVER_URL` |
| Public base URL of the frontend; what every link this app sends someone to is built from | `FRONTEND_BASE_URL` | `APP_URL`, `CLIENT_URL`, `WEB_URL` |
| Where the shared Redis instance lives; read by the rate limiter and the sign-in state store | `REDIS_URL` | `REDIS_DSN`, `CACHE_URL` |
| One pending sign-in attempt as the state store holds it: its `provider`, `nonce` and `redirect_target` | `SignInAttempt` | `OAuthState`, `PendingLogin` |
| Where sign-in attempts wait between `start` and the exchange, each consumed at most once | `SignInStateStore` (Protocol), `RedisSignInStateStore` | `StateCache`, `OAuthSessionStore` |
| Opening a sign-in attempt: mint its `state` and `nonce` and store it | `start_sign_in` | `begin_oauth`, `create_state` |
| Taking a sign-in attempt out of the store by its `state`, for the provider it was started for | `consume_sign_in_attempt` | `pop_state`, `verify_state` |
| A `state` that is unknown, spent, expired or was started for another provider | `InvalidOAuthState` | `StateMismatch`, `BadState` |
| The app-relative path a sign-in lands on afterwards; only a path starting with a single `/` is accepted | `redirect_target` (`safe_redirect_target`) | `next`, `return_to`, `redirect_url` |
| Turning a verified `ProviderIdentity` into a session, a new `user`, or a pending link | `sign_in_with_provider` | `oauth_login`, `authenticate_provider` |
| The outcomes of `sign_in_with_provider`: a session was issued, or a link confirmation email was queued | `SignedIn`, `LinkPending` | `LoginResult`, `OAuthResult` |
| A single-use token, emailed to an account's address, that confirms linking one frozen provider identity to that account | `oauth_link_token` (table `oauth_link_token`, model `OAuthLinkToken`) | `link_token`, `connect_token`, `merge_token` |
| How long an `oauth_link_token` stays valid | `OAUTH_LINK_TOKEN_EXP` | `LINK_TOKEN_TTL`, `OAUTH_LINK_EXPIRY` |
| Redeeming an `oauth_link_token`: attach its identity to its `user` | `confirm_identity_link` | `confirm_link`, `accept_link` |
| An `oauth_link_token` that is unknown or already used / past its `expires_at` | `InvalidOAuthLinkToken`, `OAuthLinkTokenExpired` | `InvalidLinkToken`, `LinkExpired` |
| Refusal: the account with this email already has a provider identity (an account holds at most one) | `EmailLinkedToOtherProvider` | `AlreadyLinked`, `ProviderConflict` |
| Which provider an account is already linked to, returned with `EmailLinkedToOtherProvider` so the client can name it | `linked_provider` | `existing_provider`, `other_provider` |
| Firing the Celery dispatch for a freshly written outbox row, tolerating a broker outage | `queue_dispatch_email` | `_queue_dispatch`, `send_async` |
| Setting both session cookies on a response, as every sign-in path does | `set_token_cookies` | `_set_token_cookies`, `add_session_cookies` |
| Frontend screen that redeems an emailed `oauth_link_token` (`{FRONTEND_BASE_URL}/link-provider-confirm?token=…`) | `link-provider-confirm` | `link-account`, `confirm-link` |
| An `AuthUiError` kind: this email's account is already linked to another provider, optionally naming it as `linkedProvider` | `oauth-email-linked-elsewhere` | `oauth-conflict`, `already-linked` |
| Whether a `/native` result is the link-pending `202` rather than a session | `isLinkPending` | `isLinkRequired`, `needsLink` |
| The web return leg's one-shot success-but-not-signed-in flag on the sign-in URL (`link_email_sent`); the counterpart of `oauth_error` | `oauth_notice` | `oauth_status`, `oauth_info` |
| A deliberate structured record of something the app did, carrying its data as fields rather than prose | `audit_event` (emitted by an `AuditLogger`) | `audit_log`, `activity`, `trace`, `analytics_event` |
| The logger every `audit_event` goes through; filter on it, or on its name as a prefix, to select the audit stream | `backend.audit` (`AUDIT_LOGGER_NAME`) | `audit_log`, `security_logger` |
| The logger one area writes its `audit_event`s through, wrapping a child of `backend.audit`: `audit.info(event, **fields)` / `audit.warning(...)` scrub `SENSITIVE_FIELDS` and nest the fields before the record exists | `AuditLogger`, made with `audit_logger(area)`, areas `auth`, `oauth`, `db` | `log_event`, `get_audit_logger`, `domain_logger`, `AUDIT_<AREA>` |
| The id shared by every log line from one request or task, used to join them | `correlation_id` | `request_id`, `trace_id`, `req_id` |
| The client address an `audit_event` came from, taken from the ASGI `client` (behind a proxy, uvicorn's `--forwarded-allow-ips` decides who to trust, never a raw `X-Forwarded-For`) | `ip_address` | `client_ip`, `remote_addr`, `ip` |
| The `User-Agent` header an `audit_event` came with, truncated to `MAX_USER_AGENT_LENGTH` | `user_agent` | `ua`, `client_agent`, `browser` |
| How a `login.succeeded` or `user.registered` came about | `method` (`password`, `oauth`) | `auth_method`, `login_type`, `via` |
| An `audit_event`: a refresh token family was signed out through `POST /auth/logout` | `logout` | `user.logged_out`, `session.ended` |
| An `audit_event`: a provider identity was attached to a `user`, with a `reason` (`new_account`, `link_confirmed`, `unverified_account_claimed`) | `oauth.identity_linked` | `oauth.linked`, `identity.created` |
| An `audit_event`: a provider sign-in matched a verified account, so an `oauth_link` email was queued | `oauth.link_requested` | `oauth.link_offered`, `link.pending` |
| An `audit_event`: a link was refused because the account or the identity already has another provider | `oauth.link_refused` | `oauth.link_denied`, `link.conflict` |
| An `audit_event` for a refresh that lost a legitimate race, distinct from `token.reuse_detected` which means theft | `token.refresh_concurrent` | `refresh_race`, `token.race_lost` |
| An `audit_event` recording one row write — table, operation, rowcount, ids, never column values | `db_write` | `db_audit`, `query_log`, `sql_event` |
| Field names never written to a log, replaced with `SCRUBBED` before the record exists | `SENSITIVE_FIELDS` | `redacted_fields`, `denylist`, `pii_fields` |
| The minimum severity the app emits | `LOG_LEVEL` | `log_verbosity`, `verbosity` |
| The shape records are written in, `json` or `console` | `LOG_FORMAT` | `log_style`, `log_output`, `formatter` |


