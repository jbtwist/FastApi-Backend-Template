/**
 * T025 — auth session state machine (SKELETON, not yet implemented).
 *
 * `AuthProvider` owns the `data-model.md` → AuthSession machine and wires
 * `api-client`'s `onSessionExpired` hook; `useAuth()` exposes it to screens.
 * Behaviour is added in the T025 implementation task — this stub exists only
 * so `auth-context.test.tsx` fails on assertions rather than on a missing
 * module.
 */
import { createContext, useContext, type ReactNode } from 'react';

export type AuthStatus = 'loading' | 'signedOut' | 'signedIn' | 'renewing' | 'expired';

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
  bootstrap: () => Promise<void>;
  signIn: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
  refreshSession: () => Promise<boolean>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const value: AuthContextValue = {
    status: 'loading',
    user: null,
    signedOutReason: null,
    bootstrap: async () => {},
    signIn: async () => {},
    register: async () => {},
    signOut: async () => {},
    refreshSession: async () => false,
  };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) {
    throw new Error('useAuth() must be used inside an <AuthProvider>');
  }
  return value;
}
