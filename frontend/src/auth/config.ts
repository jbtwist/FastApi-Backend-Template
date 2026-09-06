/**
 * Static + env-derived configuration for the authentication template.
 *
 * This is the single knob panel for reusing these screens in another app:
 * point `apiBaseUrl` at a real backend, and flip `oauthEnabled` on once the
 * backend supports third-party sign-in (see `components/auth/provider-buttons`).
 */

export type OAuthProvider = 'google' | 'apple';

export type AuthConfig = {
  /** Base URL of the `/auth` API. `EXPO_PUBLIC_API_URL` or the dev default. */
  apiBaseUrl: string;
  /** When `false`, provider buttons render but are inert ("coming soon"). */
  oauthEnabled: boolean;
  /** Providers to show, in display order. */
  providers: OAuthProvider[];
  /** Minimum password length surfaced as hint text (policy is enforced server-side). */
  passwordMinLength: number;
  /** Client-side cooldown between "resend verification email" taps, in seconds. */
  resendCooldownSeconds: number;
};

const DEFAULT_API_BASE_URL = 'http://localhost:8000';

export const authConfig: AuthConfig = {
  apiBaseUrl: process.env.EXPO_PUBLIC_API_URL ?? DEFAULT_API_BASE_URL,
  oauthEnabled: false,
  providers: ['google', 'apple'],
  passwordMinLength: 12,
  resendCooldownSeconds: 30,
};
