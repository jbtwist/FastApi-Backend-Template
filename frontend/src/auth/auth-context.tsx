/**
 * The auth session state machine.
 *
 *   loading ──bootstrap ok──▶ signedIn
 *   loading ──no / dead session──▶ signedOut
 *   signedOut ──signIn──▶ signedIn
 *   signedIn ──signOut──▶ signedOut
 *   signedIn / renewing ──refresh 401──▶ expired ──▶ signedOut  (+ signedOutReason)
 *
 * Transport, error mapping and single-flight refresh-on-401 live in
 * `api-client`; the typed calls in `auth-api`. This provider only
 * owns the machine and the platform split for "do I have a session?":
 *   - native: a token pair in `expo-secure-store` gates the `/me` probe;
 *   - web: no token is touched — `/me` succeeding *is* the session.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { Platform } from 'react-native';

import * as authApi from './auth-api';
import { configureApiClient, ensureFreshSession } from './api-client';
import * as pendingVerification from './pending-verification';
import { clearTokens, getTokens, setTokens } from './token-store';

export type AuthStatus = 'loading' | 'signedOut' | 'signedIn' | 'renewing' | 'expired';

/** Why the app dropped to `signedOut`. `'session-expired'` drives the one-shot
 *  "please sign in again" notice; `null` for a plain / first-launch sign-out. */
export type SignedOutReason = 'session-expired' | null;

export interface CurrentUser {
  id: string;
  email: string;
  emailVerified: boolean;
}

export interface AuthContextValue {
  status: AuthStatus;
  user: CurrentUser | null;
  signedOutReason: SignedOutReason;
  /** Re-run the launch probe. Called once on mount; exposed for a manual retry. */
  bootstrap: () => Promise<void>;
  /** Throws `AuthApiError` for `401` / `403` / `429`; state is untouched on throw.
   *  On success, clears the `PendingVerification` record when it names this
   *  account — signing in proves it is verified. A record naming a different
   *  account is kept, because `verify-email-confirm` still needs it. */
  signIn: (email: string, password: string) => Promise<void>;
  /** Enumeration-safe: resolves on `204`, throws `AuthApiError` on `422` / `429`.
   *  Never signs the user in — the caller routes to the verify screen. */
  register: (email: string, password: string) => Promise<void>;
  /** Best-effort server logout, then always clears local state. */
  signOut: () => Promise<void>;
  /** Explicit refresh. `true` → still `signedIn`; `false` → `expired` → `signedOut`. */
  refreshSession: () => Promise<boolean>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

const isNative = () => Platform.OS !== 'web';

function toCurrentUser(u: authApi.UserOut): CurrentUser {
  return { id: u.id, email: u.email, emailVerified: u.email_verified };
}

/** Provides the `AuthContext` to its descendants, managing the authentication state machine. */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>('loading');
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [signedOutReason, setSignedOutReason] = useState<SignedOutReason>(null);

  const goSignedOut = useCallback((reason: SignedOutReason) => {
    setUser(null);
    setStatus(reason === 'session-expired' ? 'expired' : 'signedOut');
    setSignedOutReason(reason);
    // `expired` is only a label for the transition; settle on `signedOut`.
    if (reason === 'session-expired') setStatus('signedOut');
  }, []);

  const goSignedIn = useCallback((u: authApi.UserOut) => {
    setUser(toCurrentUser(u));
    setSignedOutReason(null);
    setStatus('signedIn');
  }, []);

  const bootstrap = useCallback(async () => {
    try {
      if (isNative() && !(await getTokens())) {
        // No stored pair — nothing to validate, no network call.
        goSignedOut(null);
        return;
      }
      // `api-client` transparently refreshes + retries a `401` here; if it
      // can't recover it throws (and has already cleared native tokens).
      goSignedIn(await authApi.me());
    } catch {
      if (isNative()) await clearTokens().catch(() => undefined);
      // A failed launch probe is a clean sign-out, never a "session expired" notice.
      goSignedOut(null);
    }
  }, [goSignedIn, goSignedOut]);

  const signIn = useCallback(
    async (email: string, password: string) => {
      const out = await authApi.login({ email: email.trim(), password });
      if (isNative()) {
        await setTokens({ accessToken: out.access_token, refreshToken: out.refresh_token });
      }
      const pending = await pendingVerification.get();
      if (pending && pendingVerification.isSameEmail(pending.email, out.email)) {
        await pendingVerification.clear();
      }
      goSignedIn(out);
    },
    [goSignedIn],
  );

  const register = useCallback(async (email: string, password: string) => {
    await authApi.register({ email: email.trim(), password });
  }, []);

  const signOut = useCallback(async () => {
    try {
      const tokens = isNative() ? await getTokens() : null;
      await authApi.logout(tokens?.refreshToken);
    } catch {
      // best-effort — a dead network must not trap the user signed in
    }
    if (isNative()) await clearTokens().catch(() => undefined);
    setUser(null);
    setSignedOutReason(null);
    setStatus('signedOut');
  }, []);

  const refreshSession = useCallback(async () => {
    setStatus('renewing');
    const ok = await ensureFreshSession();
    if (ok) {
      setStatus('signedIn');
      return true;
    }
    if (isNative()) await clearTokens().catch(() => undefined);
    goSignedOut('session-expired');
    return false;
  }, [goSignedOut]);

  // Run the launch probe once. The provider mounts in `loading`, so bootstrap
  // never has to set that itself (a manual re-run stays on the current status).
  // Resolving the stored session into React state is exactly what an effect is
  // for; every setState inside `bootstrap` lands after an `await`, so the
  // "synchronous setState in an effect" heuristic is a false positive here.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void bootstrap();
  }, [bootstrap]);

  // Keep `api-client`'s expiry hook bound to the current status: only a *live*
  // session expiring earns the "please sign in again" notice — a `401` during
  // bootstrap is handled by `bootstrap`'s own catch (status is still `loading`).
  useEffect(() => {
    configureApiClient({
      onSessionExpired: () => {
        if (status === 'signedIn' || status === 'renewing') {
          goSignedOut('session-expired');
        }
      },
    });
  }, [status, goSignedOut]);

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      user,
      signedOutReason,
      bootstrap,
      signIn,
      register,
      signOut,
      refreshSession,
    }),
    [status, user, signedOutReason, bootstrap, signIn, register, signOut, refreshSession],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

/** Access the `AuthContext` to read auth status, user, and authentication actions. Must be used inside an `<AuthProvider>`. */
export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) {
    throw new Error('useAuth() must be used inside an <AuthProvider>');
  }
  return value;
}
