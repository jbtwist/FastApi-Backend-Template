/**
 * Orchestrates one third-party sign-in attempt.
 *
 * Two platform paths, one outcome (`frontend-contract.md`):
 *  - native: `/start` → the platform SDK, with the server's `nonce` → `/native`
 *    → the resulting `LoginOut` is handed to `auth-context`'s existing session
 *    machine. No new session handling (FR-038).
 *  - web: navigate to `GET /auth/oauth/{provider}/authorize`. The browser
 *    returns via the backend's redirect; no token is ever touched by web JS.
 *
 * Screens own fetching the enabled-provider list, the double-submit guard and
 * routing on the outcome; this module only runs the attempt itself.
 */
import { Platform } from 'react-native';

import * as authApi from './auth-api';
import type { OAuthProvider } from './config';
import type { AuthUiError } from './errors';

/** What a sign-in attempt ended in. */
export type OAuthOutcome =
  | { kind: 'signed-in' }
  | { kind: 'cancelled' }
  | { kind: 'navigating' }
  | { kind: 'error'; error: AuthUiError };

export interface StartOAuthSignInOptions {
  /** App-relative path to land on after a successful web return. */
  redirectTarget?: string;
  /** Hands the resulting session to `auth-context` — `completeOAuthSignIn`. */
  onSignedIn: (out: authApi.LoginOut) => Promise<void>;
}

/** `GET /auth/oauth/providers` — which providers to render buttons for (FR-040). */
export async function fetchEnabledProviders(): Promise<OAuthProvider[]> {
  throw new Error('not implemented');
}

/**
 * Run one sign-in attempt for `provider`, branching on platform.
 *
 * On native this resolves once the attempt is fully settled. On web it
 * navigates the browser away and resolves `{ kind: 'navigating' }` — real
 * users never see that value because the page has already unloaded.
 */
export async function startOAuthSignIn(
  provider: OAuthProvider,
  options: StartOAuthSignInOptions,
): Promise<OAuthOutcome> {
  throw new Error('not implemented');
}

/** `true` when this platform uses the browser-redirect path, not the native SDK. */
export function isWebOAuthPlatform(): boolean {
  return Platform.OS === 'web';
}
