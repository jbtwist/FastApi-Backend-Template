import type { ReactNode } from 'react';
import { Text } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import {
  renderRouter,
  screen,
  act,
  waitFor,
  fireEvent,
} from 'expo-router/testing-library';

import { AuthApiError } from '@/auth/api-client';
import { LocaleProvider } from '@/i18n/provider';
import { ColorSchemeProvider } from '@/theme/provider';

const mockConfirm = jest.fn<Promise<void>, [string]>();
const mockSignOut = jest.fn<Promise<void>, []>();
const mockGetPending = jest.fn<Promise<unknown>, []>();
const mockClearPending = jest.fn<Promise<void>, []>();

let mockStatus: 'loading' | 'signedOut' | 'signedIn' = 'signedOut';
let mockUser: { id: string; email: string; emailVerified: boolean } | null = null;

jest.mock('@/auth/auth-api', () => ({
  confirmEmail: (token: string) => mockConfirm(token),
}));

jest.mock('@/auth/auth-context', () => ({
  useAuth: () => ({ status: mockStatus, user: mockUser, signOut: mockSignOut }),
}));

jest.mock('@/auth/pending-verification', () => ({
  isSameEmail: jest.requireActual('@/auth/pending-verification').isSameEmail,
  get: () => mockGetPending(),
  clear: () => mockClearPending(),
  set: jest.fn().mockResolvedValue(undefined),
}));

const SAFE_AREA_METRICS = {
  frame: { x: 0, y: 0, width: 390, height: 844 },
  insets: { top: 47, left: 0, right: 0, bottom: 34 },
};

function Providers({ children }: { children: ReactNode }) {
  return (
    <SafeAreaProvider initialMetrics={SAFE_AREA_METRICS}>
      <LocaleProvider>
        <ColorSchemeProvider>{children}</ColorSchemeProvider>
      </LocaleProvider>
    </SafeAreaProvider>
  );
}

const stub = (label: string) => {
  const Stub = () => <Text>{label}</Text>;
  Stub.displayName = `Stub(${label})`;
  return Stub;
};

function routes() {
  return {
    'index': stub('root'),
    'verify-email-confirm': require('../verify-email-confirm').default,
    '(auth)/sign-in': stub('sign-in screen'),
    '(auth)/verify-email': stub('verify-email screen'),
    '(app)/index': stub('app home'),
  };
}

function mount(initialUrl: string) {
  return renderRouter(routes(), { initialUrl, wrapper: Providers });
}

beforeEach(() => {
  mockConfirm.mockReset();
  mockConfirm.mockResolvedValue(undefined);
  mockSignOut.mockReset();
  mockSignOut.mockResolvedValue(undefined);
  mockGetPending.mockReset();
  mockGetPending.mockResolvedValue(null);
  mockClearPending.mockReset();
  mockClearPending.mockResolvedValue(undefined);
  mockStatus = 'signedOut';
  mockUser = null;
});

describe('verify-email-confirm screen', () => {
  it('confirms the ?token= on mount and shows the verified state', async () => {
    const router = mount('/verify-email-confirm?token=tok-123');

    await waitFor(() => expect(mockConfirm).toHaveBeenCalledWith('tok-123'));
    expect(await screen.findByText('Email verified')).toBeOnTheScreen();

    fireEvent.press(screen.getByRole('button', { name: 'Continue' }));
    await waitFor(() => expect(router.getPathname()).toBe('/sign-in'));
  });

  it('continues into the app when a session is already active', async () => {
    mockStatus = 'signedIn';
    mockUser = { id: 'u1', email: 'me@example.com', emailVerified: false };
    mount('/verify-email-confirm?token=tok-123');

    await screen.findByText('Email verified');
    fireEvent.press(screen.getByRole('button', { name: 'Continue' }));
    await waitFor(() => expect(screen.getByText('app home')).toBeOnTheScreen());
  });

  it('400 → invalid-link state with a path back to request a new email', async () => {
    mockConfirm.mockRejectedValue(new AuthApiError({ kind: 'invalid-token' }, 400));
    const router = mount('/verify-email-confirm?token=stale');

    expect(
      await screen.findByText('This link is invalid or expired'),
    ).toBeOnTheScreen();

    fireEvent.press(screen.getByRole('button', { name: 'Request a new email' }));
    await waitFor(() => expect(router.getPathname()).toBe('/verify-email'));
  });

  it('missing token → invalid-link state, no confirm call', async () => {
    mount('/verify-email-confirm');

    expect(
      await screen.findByText('This verification link is missing its token.'),
    ).toBeOnTheScreen();
    expect(mockConfirm).not.toHaveBeenCalled();
  });

  it('confirms without a conflict when the pending email differs only in case', async () => {
    mockStatus = 'signedIn';
    mockUser = { id: 'u1', email: 'alice@example.com', emailVerified: true };
    mockGetPending.mockResolvedValue({ email: 'Alice@Example.com', lastSentAt: Date.now() });

    mount('/verify-email-confirm?token=tok-123');

    await waitFor(() => expect(mockConfirm).toHaveBeenCalledWith('tok-123'));
    expect(screen.queryByText('A different account is signed in')).toBeNull();
  });

  it('prompts to resolve the conflict when a different user is signed in', async () => {
    mockStatus = 'signedIn';
    mockUser = { id: 'u1', email: 'me@example.com', emailVerified: true };
    mockGetPending.mockResolvedValue({ email: 'other@example.com', lastSentAt: Date.now() });

    mount('/verify-email-confirm?token=tok-123');

    expect(
      await screen.findByText('A different account is signed in'),
    ).toBeOnTheScreen();
    expect(
      screen.getByText(
        "You're signed in as me@example.com. Continue as this user, or sign out to verify the other email.",
      ),
    ).toBeOnTheScreen();
    expect(mockConfirm).not.toHaveBeenCalled();
  });

  it('conflict → "sign out and verify" signs out then confirms the token', async () => {
    mockStatus = 'signedIn';
    mockUser = { id: 'u1', email: 'me@example.com', emailVerified: true };
    mockGetPending.mockResolvedValue({ email: 'other@example.com', lastSentAt: Date.now() });

    mount('/verify-email-confirm?token=tok-123');
    await screen.findByText('A different account is signed in');

    await act(async () => {
      fireEvent.press(screen.getByRole('button', { name: 'Sign out and verify' }));
    });

    expect(mockSignOut).toHaveBeenCalled();
    await waitFor(() => expect(mockConfirm).toHaveBeenCalledWith('tok-123'));
  });

  it('conflict → "continue as" the signed-in user drops into the app', async () => {
    mockStatus = 'signedIn';
    mockUser = { id: 'u1', email: 'me@example.com', emailVerified: true };
    mockGetPending.mockResolvedValue({ email: 'other@example.com', lastSentAt: Date.now() });

    mount('/verify-email-confirm?token=tok-123');
    await screen.findByText('A different account is signed in');

    fireEvent.press(screen.getByRole('button', { name: 'Continue as me@example.com' }));
    await waitFor(() => expect(screen.getByText('app home')).toBeOnTheScreen());
  });
});
