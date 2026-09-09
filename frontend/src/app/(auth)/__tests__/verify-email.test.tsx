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

const mockResend = jest.fn<Promise<void>, [string]>();
const mockGetPending = jest.fn<Promise<unknown>, []>();
const mockSetPending = jest.fn<Promise<void>, [unknown]>();

jest.mock('@/auth/auth-api', () => ({
  resendVerification: (email: string) => mockResend(email),
}));

jest.mock('@/auth/pending-verification', () => ({
  get: () => mockGetPending(),
  set: (value: unknown) => mockSetPending(value),
  clear: jest.fn().mockResolvedValue(undefined),
}));

const SAFE_AREA_METRICS = {
  frame: { x: 0, y: 0, width: 390, height: 844 },
  insets: { top: 47, left: 0, right: 0, bottom: 34 },
};

function Providers({ children }: { children: ReactNode }) {
  return (
    <SafeAreaProvider initialMetrics={SAFE_AREA_METRICS}>
      <LocaleProvider>{children}</LocaleProvider>
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
    '(auth)/verify-email': require('../verify-email').default,
    '(auth)/sign-in': stub('sign-in screen'),
  };
}

function mount(initialUrl = '/verify-email') {
  return renderRouter(routes(), { initialUrl, wrapper: Providers });
}

beforeEach(() => {
  mockResend.mockReset();
  mockResend.mockResolvedValue(undefined);
  mockSetPending.mockReset();
  mockSetPending.mockResolvedValue(undefined);
  mockGetPending.mockReset();
  mockGetPending.mockResolvedValue({
    email: 'new@example.com',
    lastSentAt: Date.now() - 60_000, // well past the 30s cooldown
  });
});

describe('verify-email screen', () => {
  it('names the pending address and explains both next steps', async () => {
    mount();

    expect(
      await screen.findByText(
        'We sent a verification link to new@example.com. Open it to finish setting up your account.',
      ),
    ).toBeOnTheScreen();
    expect(
      screen.getByText('Tap the link in that email on this device to verify.'),
    ).toBeOnTheScreen();
    expect(
      screen.getByText(
        'You can also sign in or reset your password from here once your email is verified.',
      ),
    ).toBeOnTheScreen();
  });

  it('falls back to the ?email= param when there is no stored record', async () => {
    mockGetPending.mockResolvedValue(null);
    mount('/verify-email?email=param@example.com');

    expect(
      await screen.findByText(
        'We sent a verification link to param@example.com. Open it to finish setting up your account.',
      ),
    ).toBeOnTheScreen();
  });

  it('resends the verification email, then throttles the button', async () => {
    mount();
    await screen.findByText(/We sent a verification link to new@example.com/);

    await act(async () => {
      fireEvent.press(screen.getByRole('button', { name: 'Resend email' }));
    });

    expect(mockResend).toHaveBeenCalledWith('new@example.com');
    expect(mockSetPending).toHaveBeenCalledWith(
      expect.objectContaining({ email: 'new@example.com', lastSentAt: expect.any(Number) }),
    );
    expect(screen.getByText('Verification email sent.')).toBeOnTheScreen();
    await waitFor(() =>
      expect(
        screen.getByRole('button', { name: 'Resend email' }).props.accessibilityState,
      ).toMatchObject({ disabled: true }),
    );
  });

  it('starts throttled when the stored record is inside the cooldown window', async () => {
    mockGetPending.mockResolvedValue({ email: 'new@example.com', lastSentAt: Date.now() });
    mount();
    await screen.findByText(/We sent a verification link to new@example.com/);

    await waitFor(() =>
      expect(
        screen.getByRole('button', { name: 'Resend email' }).props.accessibilityState,
      ).toMatchObject({ disabled: true }),
    );
    expect(mockResend).not.toHaveBeenCalled();
  });

  it('surfaces a rate-limited message when resend returns 429', async () => {
    mockResend.mockRejectedValue(new AuthApiError({ kind: 'rate-limited' }, 429));
    mount();
    await screen.findByText(/We sent a verification link to new@example.com/);

    await act(async () => {
      fireEvent.press(screen.getByRole('button', { name: 'Resend email' }));
    });

    expect(
      screen.getByText('Too many attempts. Please try again later.'),
    ).toBeOnTheScreen();
  });

  it('routes back to sign in from the link', async () => {
    const router = mount();
    await screen.findByText(/We sent a verification link to new@example.com/);

    fireEvent.press(screen.getByText('Back to sign in'));
    await waitFor(() => expect(router.getPathname()).toBe('/sign-in'));
  });
});
