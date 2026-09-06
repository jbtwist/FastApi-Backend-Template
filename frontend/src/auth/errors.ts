/**
 * Maps backend `/auth` failures onto the small set of outcomes the screens
 * actually render. Source of truth: `specs/002-auth-frontend-flows/contracts/auth-api.md`
 * ("Client error union" + "Mapping rules").
 *
 * This module holds no user-facing copy — screens map each `AuthUiError` kind
 * to a message in `i18n/locales`. The one exception is `password-policy.message`,
 * which carries the server `detail` verbatim.
 */

/** Which call produced the failure — the mapping depends on it. */
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
  /** any other authenticated request routed through the api-client */
  | 'authed';

export type AuthUiError =
  | { kind: 'invalid-credentials' }
  | { kind: 'email-not-verified'; email: string }
  | { kind: 'password-policy'; message: string }
  | { kind: 'invalid-token' }
  | { kind: 'rate-limited'; retryAfterSeconds?: number }
  | { kind: 'offline' }
  | { kind: 'timeout' }
  | { kind: 'unknown' };

export interface ToAuthUiErrorOptions {
  /** Email typed into the form — attached to `email-not-verified` (403 on login). */
  submittedEmail?: string;
  /** Seconds from a parsed `Retry-After` header — attached to `rate-limited` (429). */
  retryAfterSeconds?: number;
}

const PASSWORD_POLICY_FALLBACK = 'This password is not allowed. Choose another.';

const INVALID_TOKEN_CONTEXTS: ReadonlySet<AuthEndpointContext> = new Set([
  'confirm-email',
  'reset-password',
]);

const PASSWORD_POLICY_CONTEXTS: ReadonlySet<AuthEndpointContext> = new Set([
  'register',
  'reset-password',
]);

/**
 * Turn an HTTP status + optional `detail` string into an `AuthUiError`.
 *
 * Returns `null` when the status is not a UI concern — a `401` on `me` /
 * `refresh` / `logout` / an authed call drives the refresh-or-sign-out logic in
 * `api-client`/`auth-context`, not a banner.
 */
export function toAuthUiError(
  status: number,
  detail: string | undefined,
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
      // me / refresh / logout / authed → handled by session logic.
      return null;

    case 403:
      if (context === 'login') {
        return { kind: 'email-not-verified', email: options.submittedEmail ?? '' };
      }
      return { kind: 'unknown' };

    case 422:
      if (PASSWORD_POLICY_CONTEXTS.has(context)) {
        const trimmed = detail?.trim();
        return {
          kind: 'password-policy',
          message: trimmed && trimmed.length > 0 ? trimmed : PASSWORD_POLICY_FALLBACK,
        };
      }
      return { kind: 'unknown' };

    case 429:
      return options.retryAfterSeconds === undefined
        ? { kind: 'rate-limited' }
        : { kind: 'rate-limited', retryAfterSeconds: options.retryAfterSeconds };

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
