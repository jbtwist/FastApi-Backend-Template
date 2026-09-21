/**
 * Orchestrates one third-party sign-in attempt.
 *
 * Two platform paths, one outcome:
 *  - native: `/start` → the platform SDK, with the server's `nonce` → `/native`
 *    → the resulting `LoginOut` is handed to `auth-context`'s existing session
 *    machine, with no new session handling. When the provider's email belongs
 *    to an existing account, `/native` answers `202` instead: that account was
 *    emailed a link to confirm, and the attempt ends in `link-email-sent`.
 *  - web: navigate to `GET /auth/oauth/{provider}/authorize`. The browser
 *    returns via the backend's redirect; no token is ever touched by web JS.
 *
 * Screens own fetching the enabled-provider list, the double-submit guard and
 * routing on the outcome; this module only runs the attempt itself.
 *
 * Google only: the native path never runs for Apple (2026-09-12) — Sign in
 * with Apple needs a paid Apple Developer Program membership this project
 * doesn't have. `apple` still resolves through the web path, once a backend
 * lists it.
 */
import { Platform } from 'react-native';
import * as AuthSession from 'expo-auth-session';
import { discovery as googleDiscovery } from 'expo-auth-session/providers/google';

import * as authApi from './auth-api';
import { authConfig, type OAuthProvider } from './config';
import type { AuthUiError } from './errors';
import { AuthApiError } from './api-client';

/** What a sign-in attempt ended in. */
export type OAuthOutcome =
  | { kind: 'signed-in' }
  | { kind: 'link-email-sent' }
  | { kind: 'cancelled' }
  | { kind: 'navigating' }
  | { kind: 'error'; error: AuthUiError };

export interface StartOAuthSignInOptions {
  /** App-relative path to land on after a successful web return. */
  redirectTarget?: string;
  /** Hands the resulting session to `auth-context` — `completeOAuthSignIn`. */
  onSignedIn: (out: authApi.LoginOut) => Promise<void>;
}

/** `GET /auth/oauth/providers` — which providers to render buttons for. */
export async function fetchEnabledProviders(): Promise<OAuthProvider[]> {
  const { providers } = await authApi.oauthProviders();
  return providers;
}

/** `true` when this platform uses the browser-redirect path, not the native SDK. */
export function isWebOAuthPlatform(): boolean {
  return Platform.OS === 'web';
}

function googleClientIdForPlatform(): string | undefined {
  const { web, ios, android } = authConfig.googleClientIds;
  if (Platform.OS === 'web') return web;
  if (Platform.OS === 'ios') return ios;
  if (Platform.OS === 'android') return android;
  return undefined;
}

/** Internal result of running the platform SDK + `/native` exchange. */
type NativeSignInResult =
  | { kind: 'signed-in'; out: authApi.LoginOut }
  | { kind: 'link-email-sent' }
  | { kind: 'cancelled' }
  | { kind: 'error'; error: AuthUiError };

/**
 * Run the Google native flow: prompt the platform SDK with the server's
 * `nonce`, then trade the resulting ID token for a `LoginOut` at `/native`.
 */
async function runGoogleNativeSignIn(state: string, nonce: string): Promise<NativeSignInResult> {
  const clientId = googleClientIdForPlatform();
  if (!clientId) return { kind: 'error', error: { kind: 'oauth-unavailable' } };

  const request = new AuthSession.AuthRequest({
    clientId,
    redirectUri: AuthSession.makeRedirectUri(),
    responseType: AuthSession.ResponseType.IdToken,
    scopes: ['openid', 'email', 'profile'],
    extraParams: { nonce },
  });

  const result = await request.promptAsync(googleDiscovery);

  if (result.type === 'cancel' || result.type === 'dismiss') {
    return { kind: 'cancelled' };
  }
  if (result.type === 'error') {
    // Google returns the consent screen's "Cancel" as an `access_denied`
    // error, not a `cancel`/`dismiss` result — treat it the same: a normal
    // act, not a failure.
    return result.params?.error === 'access_denied'
      ? { kind: 'cancelled' }
      : { kind: 'error', error: { kind: 'oauth-failed' } };
  }
  if (result.type !== 'success') {
    // 'opened' / 'locked' — the request could not even be shown.
    return { kind: 'error', error: { kind: 'oauth-failed' } };
  }

  const idToken = result.authentication?.idToken ?? result.params.id_token;
  if (!idToken) return { kind: 'error', error: { kind: 'oauth-failed' } };

  try {
    const out = await authApi.oauthNative('google', { state, assertion: idToken });
    return authApi.isLinkPending(out) ? { kind: 'link-email-sent' } : { kind: 'signed-in', out };
  } catch (error) {
    if (error instanceof AuthApiError) return { kind: 'error', error: error.uiError };
    return { kind: 'error', error: { kind: 'unknown' } };
  }
}

function authorizeUrl(provider: OAuthProvider, redirectTarget?: string): string {
  const query = redirectTarget ? `?redirect_target=${encodeURIComponent(redirectTarget)}` : '';
  return `${authConfig.apiBaseUrl}/auth/oauth/${provider}/authorize${query}`;
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
  if (isWebOAuthPlatform()) {
    if (typeof window !== 'undefined') {
      window.location.href = authorizeUrl(provider, options.redirectTarget);
    }
    return { kind: 'navigating' };
  }

  if (provider !== 'google') {
    // No native path exists for any other provider (2026-09-12).
    return { kind: 'error', error: { kind: 'oauth-unavailable' } };
  }

  let start: authApi.OAuthStartOut;
  try {
    start = await authApi.oauthStart(provider, options.redirectTarget);
  } catch (error) {
    if (error instanceof AuthApiError) return { kind: 'error', error: error.uiError };
    return { kind: 'error', error: { kind: 'unknown' } };
  }

  const outcome = await runGoogleNativeSignIn(start.state, start.nonce);
  if (outcome.kind === 'signed-in') {
    await options.onSignedIn(outcome.out);
    return { kind: 'signed-in' };
  }
  return outcome;
}
