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

const mockForgotPassword = jest.fn<Promise<void>, [string]>();

jest.mock('@/auth/auth-api', () => ({
  forgotPassword: (email: string) => mockForgotPassword(email),
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
    '(auth)/forgot-password': require('../forgot-password').default,
    '(auth)/sign-in': stub('sign-in screen'),
  };
}

function mount() {
  return renderRouter(routes(), { initialUrl: '/forgot-password', wrapper: Providers });
}

async function submitEmail(email: string) {
  fireEvent.changeText(screen.getByLabelText('Email'), email);
  await act(async () => {
    fireEvent.press(screen.getByRole('button', { name: 'Send reset link' }));
  });
}

beforeEach(() => {
  mockForgotPassword.mockReset();
  mockForgotPassword.mockResolvedValue(undefined);
});

describe('forgot-password screen', () => {
  it('sends a trimmed address then shows the enumeration-safe confirmation', async () => {
    mount();

    await submitEmail('  person@example.com  ');

    expect(mockForgotPassword).toHaveBeenCalledWith('person@example.com');
    expect(await screen.findByText('Check your email')).toBeOnTheScreen();
    expect(
      screen.getByText('If that address has an account, a reset link is on its way.'),
    ).toBeOnTheScreen();
  });

  it('rejects a malformed address on the field without calling the API', async () => {
    mount();

    await submitEmail('not-an-email');

    expect(mockForgotPassword).not.toHaveBeenCalled();
    expect(await screen.findByText('Enter a valid email address.')).toBeOnTheScreen();
  });

  it('maps a 422 on the address to a field error', async () => {
    mockForgotPassword.mockRejectedValue(new AuthApiError({ kind: 'invalid-email' }, 422));
    mount();

    await submitEmail('person@example.com');

    expect(await screen.findByText('Enter a valid email address.')).toBeOnTheScreen();
    expect(screen.queryByText('Check your email')).not.toBeOnTheScreen();
  });

  it('shows a form banner when the request is rate limited', async () => {
    mockForgotPassword.mockRejectedValue(new AuthApiError({ kind: 'rate-limited' }, 429));
    mount();

    await submitEmail('person@example.com');

    expect(
      await screen.findByText('Too many attempts. Please try again later.'),
    ).toBeOnTheScreen();
  });

  it('routes back to sign in from the link', async () => {
    const router = mount();

    fireEvent.press(screen.getByText('Back to sign in'));
    await waitFor(() => expect(router.getPathname()).toBe('/sign-in'));
  });
});
