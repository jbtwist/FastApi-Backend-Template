/**
 * Static + env-derived configuration for the authentication template.
 *
 * This is the single knob panel for reusing these screens in another app:
 * point `apiBaseUrl` at a real backend, and flip `oauthEnabled` on once the
 * backend supports third-party sign-in (see `components/auth/provider-buttons`).
 *
 * Every `EXPO_PUBLIC_*` value here is substituted textually by Expo when the
 * bundle is built, not read at startup. A shipped build therefore keeps the
 * values it was built with until it is rebuilt — changing the server's
 * environment cannot reach an app already installed on a device.
 */

export type OAuthProvider = 'google' | 'apple';

export type AuthConfig = {
  /** Base URL of the `/auth` API. `EXPO_PUBLIC_API_URL` or the dev default. */
  apiBaseUrl: string;
  /** When `false`, provider buttons render but are inert ("coming soon"). */
  oauthEnabled: boolean;
  /** Providers to show, in display order. */
  providers: OAuthProvider[];
  /**
   * Shortest password the register form will submit.
   * `EXPO_PUBLIC_PASSWORD_MIN_LENGTH`, defaulting to 12.
   *
   * Must equal the server's floor, which it derives from
   * `PASSWORD_STRENGTH` (low = 8, medium = 12, high = 15). Set it too low
   * and a length rejection arrives as a `password-policy` error the screen
   * cannot tell apart from a breached password. See `auth/errors`.
   */
  passwordMinLength: number;
  /**
   * Longest password the register form will submit.
   * `EXPO_PUBLIC_PASSWORD_MAX_LENGTH`, defaulting to 128.
   *
   * Must equal the server's `PASSWORD_MAX_LENGTH`, for the same reason as
   * `passwordMinLength` above.
   */
  passwordMaxLength: number;
  /** Client-side cooldown between "resend verification email" taps, in seconds. */
  resendCooldownSeconds: number;
};

const DEFAULT_API_BASE_URL = 'http://localhost:8000';
const DEFAULT_PASSWORD_MIN_LENGTH = 12;
const DEFAULT_PASSWORD_MAX_LENGTH = 128;

/**
 * Read a positive-integer env var, falling back when it is unset or malformed.
 *
 * An unparseable value falls back rather than throwing, so a typo in `.env`
 * degrades to the stricter built-in default instead of disabling a check.
 *
 * @param raw The env value. Pass `process.env.EXPO_PUBLIC_*` as a literal —
 *   Expo substitutes those expressions textually, so a dynamic lookup reads
 *   nothing.
 * @param fallback Used when `raw` is absent, non-numeric, fractional, or <= 0.
 */
function positiveIntFromEnv(raw: string | undefined, fallback: number): number {
  const parsed = Number(raw);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : fallback;
}

export const authConfig: AuthConfig = {
  apiBaseUrl: process.env.EXPO_PUBLIC_API_URL ?? DEFAULT_API_BASE_URL,
  oauthEnabled: false,
  providers: ['google', 'apple'],
  passwordMinLength: positiveIntFromEnv(
    process.env.EXPO_PUBLIC_PASSWORD_MIN_LENGTH,
    DEFAULT_PASSWORD_MIN_LENGTH,
  ),
  passwordMaxLength: positiveIntFromEnv(
    process.env.EXPO_PUBLIC_PASSWORD_MAX_LENGTH,
    DEFAULT_PASSWORD_MAX_LENGTH,
  ),
  resendCooldownSeconds: 30,
};
