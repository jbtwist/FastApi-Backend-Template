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

const mockResetPassword = jest.fn<Promise<void>, [{ token: string; new_password: string }]>();
const mockSignOut = jest.fn<Promise<void>, []>();

let mockStatus: 'loading' | 'signedOut' | 'signedIn' = 'signedOut';
let mockUser: { id: string; email: string; emailVerified: boolean } | null = null;

jest.mock('@/auth/auth-api', () => ({
  resetPassword: (body: { token: string; new_password: string }) => mockResetPassword(body),
}));

jest.mock('@/auth/auth-context', () => ({
  useAuth: () => ({ status: mockStatus, user: mockUser, signOut: mockSignOut }),
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
    'reset-password': require('../reset-password').default,
    '(auth)/sign-in': stub('sign-in screen'),
    '(auth)/forgot-password': stub('forgot-password screen'),
    '(app)/index': stub('app home'),
  };
}

function mount(initialUrl: string) {
  return renderRouter(routes(), { initialUrl, wrapper: Providers });
}

const NEW_PASSWORD = 'brand-new-passphrase';

async function submitPassword(value: string) {
  fireEvent.changeText(screen.getByLabelText('New password'), value);
  await act(async () => {
    fireEvent.press(screen.getByRole('button', { name: 'Save new password' }));
  });
}

beforeEach(() => {
  mockResetPassword.mockReset();
  mockResetPassword.mockResolvedValue(undefined);
  mockSignOut.mockReset();
  mockSignOut.mockResolvedValue(undefined);
  mockStatus = 'signedOut';
  mockUser = null;
});

describe('reset-password screen', () => {
  it('sets a new password with the ?token= and shows the success state', async () => {
    const router = mount('/reset-password?token=tok-123');

    await submitPassword(NEW_PASSWORD);

    expect(mockResetPassword).toHaveBeenCalledWith({
      token: 'tok-123',
      new_password: NEW_PASSWORD,
    });
    expect(await screen.findByText('Password updated')).toBeOnTheScreen();

    fireEvent.press(screen.getByRole('button', { name: 'Back to sign in' }));
    await waitFor(() => expect(router.getPathname()).toBe('/sign-in'));
  });

  it('missing token → invalid-link state, and never calls the API', async () => {
    const router = mount('/reset-password');

    expect(await screen.findByText('This link is invalid or expired')).toBeOnTheScreen();
    expect(mockResetPassword).not.toHaveBeenCalled();

    fireEvent.press(screen.getByRole('button', { name: 'Start over' }));
    await waitFor(() => expect(router.getPathname()).toBe('/forgot-password'));
  });

  it('400 on submit → invalid-link state', async () => {
    mockResetPassword.mockRejectedValue(new AuthApiError({ kind: 'invalid-token' }, 400));
    mount('/reset-password?token=stale');

    await submitPassword(NEW_PASSWORD);

    expect(await screen.findByText('This link is invalid or expired')).toBeOnTheScreen();
  });

  it('rejects a too-short password on the field without calling the API', async () => {
    mount('/reset-password?token=tok-123');

    await submitPassword('short');

    expect(mockResetPassword).not.toHaveBeenCalled();
    expect(await screen.findByText('Must be at least 12 characters.')).toBeOnTheScreen();
  });

  it('maps a 422 policy rejection to the breach message on the field', async () => {
    mockResetPassword.mockRejectedValue(new AuthApiError({ kind: 'password-policy' }, 422));
    mount('/reset-password?token=tok-123');

    await submitPassword(NEW_PASSWORD);

    expect(
      await screen.findByText(
        'This password has appeared in a data breach. Choose a different one.',
      ),
    ).toBeOnTheScreen();
  });

  it('shows a form banner when the request is rate limited', async () => {
    mockResetPassword.mockRejectedValue(new AuthApiError({ kind: 'rate-limited' }, 429));
    mount('/reset-password?token=tok-123');

    await submitPassword(NEW_PASSWORD);

    expect(
      await screen.findByText('Too many attempts. Please try again later.'),
    ).toBeOnTheScreen();
  });

  it('warns when a different account is signed in, then continues as that user', async () => {
    mockStatus = 'signedIn';
    mockUser = { id: 'u1', email: 'me@example.com', emailVerified: true };

    mount('/reset-password?token=tok-123');

    expect(await screen.findByText('A different account is signed in')).toBeOnTheScreen();
    expect(
      screen.getByText(
        "You're signed in as me@example.com. Continue as this user, or sign out to reset the other account's password.",
      ),
    ).toBeOnTheScreen();

    fireEvent.press(screen.getByRole('button', { name: 'Continue as me@example.com' }));
    await waitFor(() => expect(screen.getByText('app home')).toBeOnTheScreen());
    expect(mockResetPassword).not.toHaveBeenCalled();
  });

  it('conflict → "sign out and reset" signs out then reveals the form', async () => {
    mockStatus = 'signedIn';
    mockUser = { id: 'u1', email: 'me@example.com', emailVerified: true };

    mount('/reset-password?token=tok-123');
    await screen.findByText('A different account is signed in');

    await act(async () => {
      fireEvent.press(screen.getByRole('button', { name: 'Sign out and reset' }));
    });

    expect(mockSignOut).toHaveBeenCalled();
    await submitPassword(NEW_PASSWORD);
    expect(mockResetPassword).toHaveBeenCalledWith({
      token: 'tok-123',
      new_password: NEW_PASSWORD,
    });
  });
});
