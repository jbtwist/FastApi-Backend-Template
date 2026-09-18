/**
 * Maps backend `/auth` failures onto the small set of outcomes the screens
 * actually render.
 *
 * This module holds no user-facing copy, and no server copy either: an error is
 * identified by its status and the endpoint that produced it, then screens map
 * the resulting kind to a translated message in `i18n/locales`. Nothing the
 * backend writes reaches the user, so every message follows the app's language.
 *
 * Adding a kind takes four steps:
 *
 * 1. Add the variant to {@link AuthUiError}, with a payload only for a value the
 *    catalogue cannot supply — an address to echo, a retry countdown. Never a
 *    message.
 * 2. Return it from {@link toAuthUiError} for the right status *and* context;
 *    the same status means different things per endpoint.
 * 3. Add the key to both `i18n/locales/en/errors.json` and `es/errors.json`.
 *    Spanish is type-checked against English, so a missing one fails
 *    `npm run typecheck`.
 * 4. Map the kind to that key in each screen that can produce it. Screens keep
 *    their own `messageKeyFor`, so two can word one failure differently — on the
 *    field when the failure names one, in the `FormMessage` banner otherwise.
 */

import type { OAuthProvider } from './config';

export type AuthEndpointContext =
  | 'login'
  | 'register'
  | 'me'
  | 'refresh'
  | 'logout'
  | 'confirm-email'
  | 'resend-verification'
  | 'forgot-password'
  | 'reset-password'
  | 'authed'
  | 'oauth'
  | 'oauth-link-confirm';

/** The `oauth_error` query flag the web return leg appends to the sign-in URL. */
export type OAuthErrorCode =
  | 'cancelled'
  | 'failed'
  | 'unavailable'
  | 'email_not_verified_by_provider'
  | 'email_linked_to_other_provider';

const KNOWN_PROVIDERS: ReadonlySet<string> = new Set<OAuthProvider>(['google', 'apple']);

/**
 * Narrow a provider name the backend sent to one the app has a label for.
 * Anything else is dropped rather than rendered, so the message falls back to
 * its generic wording.
 */
function asOAuthProvider(value: unknown): OAuthProvider | undefined {
  return typeof value === 'string' && KNOWN_PROVIDERS.has(value)
    ? (value as OAuthProvider)
    : undefined;
}

function linkedElsewhere(linkedProvider: unknown): AuthUiError {
  const provider = asOAuthProvider(linkedProvider);
  return provider
    ? { kind: 'oauth-email-linked-elsewhere', linkedProvider: provider }
    : { kind: 'oauth-email-linked-elsewhere' };
}

/**
 * A rendered auth failure, identified only by what the app can derive itself.
 *
 * A kind carries a payload only when the screen needs a value the catalogue
 * cannot supply — an address to echo, a countdown to show. None of them carries
 * a message: the screen picks that from `i18n/locales`.
 *
 * `password-policy` deliberately does not say *which* rule was broken. The
 * server has three (too short, too long, breached) and distinguishes them only
 * in English prose. Screens that pre-validate both lengths against
 * `authConfig.passwordMinLength` and `authConfig.passwordMaxLength` are
 * therefore left with one possible cause — the breach check — and can name it
 * in the user's language.
 */
export type AuthUiError =
  | { kind: 'invalid-credentials' }
  | { kind: 'email-not-verified'; email: string }
  | { kind: 'password-policy' }
  | { kind: 'invalid-email' }
  | { kind: 'invalid-token' }
  | { kind: 'rate-limited'; retryAfterSeconds?: number }
  | { kind: 'offline' }
  | { kind: 'timeout' }
  | { kind: 'unknown' }
  | { kind: 'oauth-cancelled' }
  | { kind: 'oauth-failed' }
  | { kind: 'oauth-unavailable' }
  | { kind: 'oauth-not-enabled' }
  | { kind: 'oauth-email-unverified' }
  | { kind: 'oauth-email-linked-elsewhere'; linkedProvider?: OAuthProvider };

export interface ToAuthUiErrorOptions {
  /** Email typed into the form — attached to `email-not-verified` (403 on login). */
  submittedEmail?: string;
  /** Seconds from a parsed `Retry-After` header — attached to `rate-limited` (429). */
  retryAfterSeconds?: number;
  /** The body's `linked_provider` — attached to `oauth-email-linked-elsewhere` (409). */
  linkedProvider?: unknown;
}

const INVALID_TOKEN_CONTEXTS: ReadonlySet<AuthEndpointContext> = new Set([
  'confirm-email',
  'reset-password',
  'oauth-link-confirm',
]);

const PASSWORD_POLICY_CONTEXTS: ReadonlySet<AuthEndpointContext> = new Set([
  'register',
  'reset-password',
]);

/**
 * Field names a schema violation points at — `loc: ['body', 'email']` yields
 * `'email'`. Empty for any other `detail` shape.
 */
function invalidFields(detail: unknown): string[] {
  if (!Array.isArray(detail)) return [];
  return detail.flatMap((item) => {
    const loc = (item as { loc?: unknown })?.loc;
    if (!Array.isArray(loc)) return [];
    const field = loc[loc.length - 1];
    return typeof field === 'string' && field !== 'body' ? [field] : [];
  });
}

/**
 * Turn an HTTP status + the response body's `detail` into an {@link AuthUiError}.
 *
 * `detail` is read for its *shape*, never its text: a list is FastAPI's own
 * schema violation and names the offending field, so a `422` mentioning `email`
 * becomes `invalid-email` rather than a password rejection. Any other shape on a
 * password endpoint is a policy rejection, and the prose it carries is dropped.
 *
 * @param status HTTP status from the response.
 * @param detail The response body's `detail`, inspected structurally.
 * @param context Endpoint that produced the failure. The same status means
 *   different things per endpoint — a `400` is only a bad token on the two
 *   token-consuming endpoints, and a `422` is only a password rejection on the
 *   two that set a password.
 * @param options Values the caller holds that the response does not.
 * @returns The error to render, or `null` when the status is not a UI concern —
 *   a `401` on `me` / `refresh` / `logout` / an authed call drives the
 *   refresh-or-sign-out logic in `api-client`/`auth-context`, not a banner.
 */
export function toAuthUiError(
  status: number,
  detail: unknown,
  context: AuthEndpointContext,
  options: ToAuthUiErrorOptions = {},
): AuthUiError | null {
  switch (status) {
    case 400:
      return INVALID_TOKEN_CONTEXTS.has(context)
        ? { kind: 'invalid-token' }
        : { kind: 'unknown' };

    case 401:
      if (context === 'login') return { kind: 'invalid-credentials' };
      if (context === 'oauth') return { kind: 'oauth-failed' };
      return null;

    case 403:
      if (context === 'login') {
        return { kind: 'email-not-verified', email: options.submittedEmail ?? '' };
      }
      if (context === 'oauth') return { kind: 'oauth-email-unverified' };
      return { kind: 'unknown' };

    case 404:
      return context === 'oauth' ? { kind: 'oauth-not-enabled' } : { kind: 'unknown' };

    case 409:
      return context === 'oauth' || context === 'oauth-link-confirm'
        ? linkedElsewhere(options.linkedProvider)
        : { kind: 'unknown' };

    case 422: {
      const fields = invalidFields(detail);
      if (fields.length > 0) {
        return fields.includes('email') ? { kind: 'invalid-email' } : { kind: 'unknown' };
      }

      return PASSWORD_POLICY_CONTEXTS.has(context)
        ? { kind: 'password-policy' }
        : { kind: 'unknown' };
    }

    case 429:
      return options.retryAfterSeconds === undefined
        ? { kind: 'rate-limited' }
        : { kind: 'rate-limited', retryAfterSeconds: options.retryAfterSeconds };

    case 503:
      return context === 'oauth' ? { kind: 'oauth-unavailable' } : { kind: 'unknown' };

    default:
      return { kind: 'unknown' };
  }
}

/**
 * Turn the web return leg's `oauth_error` query flag into an {@link AuthUiError}.
 * `cancelled` is not shown as a banner — the screen checks for that kind and
 * stays quiet, the same as a dismissed native provider sheet.
 *
 * @param code The `oauth_error` value read from the URL.
 * @param linkedProvider The `linked_provider` flag that accompanies
 *   `email_linked_to_other_provider`.
 */
export function oauthErrorCodeToAuthUiError(
  code: OAuthErrorCode | string,
  linkedProvider?: string,
): AuthUiError {
  switch (code) {
    case 'cancelled':
      return { kind: 'oauth-cancelled' };
    case 'failed':
      return { kind: 'oauth-failed' };
    case 'unavailable':
      return { kind: 'oauth-unavailable' };
    case 'email_not_verified_by_provider':
      return { kind: 'oauth-email-unverified' };
    case 'email_linked_to_other_provider':
      return linkedElsewhere(linkedProvider);
    default:
      return { kind: 'unknown' };
  }
}

/**
 * Map a thrown transport error (no HTTP response) onto `offline` / `timeout`.
 * `fetch` rejects with a `TypeError` when it cannot reach the network; an
 * `AbortController` timeout rejects with an `AbortError`.
 */
export function networkErrorToAuthUiError(error: unknown): AuthUiError {
  if (error instanceof Error && error.name === 'AbortError') {
    return { kind: 'timeout' };
  }
  if (error instanceof TypeError) {
    return { kind: 'offline' };
  }
  return { kind: 'unknown' };
}

/**
 * Parse a `Retry-After` header value into whole seconds.
 * Accepts either a delta-seconds integer or an HTTP-date; a past date clamps
 * to `0`. Returns `undefined` when the value is absent or unparseable.
 */
export function parseRetryAfter(headerValue: string | null | undefined): number | undefined {
  if (headerValue === null || headerValue === undefined) return undefined;
  const value = headerValue.trim();
  if (value === '') return undefined;

  if (/^\d+$/.test(value)) {
    return Number.parseInt(value, 10);
  }

  const dateMs = Date.parse(value);
  if (Number.isNaN(dateMs)) return undefined;
  return Math.max(0, Math.round((dateMs - Date.now()) / 1000));
}
