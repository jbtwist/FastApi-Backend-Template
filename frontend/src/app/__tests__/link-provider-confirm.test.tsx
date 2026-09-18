import type { ReactNode } from 'react';
import { Text } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { renderRouter, screen, waitFor, fireEvent } from 'expo-router/testing-library';

import { AuthApiError } from '@/auth/api-client';
import { LocaleProvider } from '@/i18n/provider';
import { ColorSchemeProvider } from '@/theme/provider';

const mockConfirmLink = jest.fn<Promise<void>, [string]>();

let mockStatus: 'loading' | 'signedOut' | 'signedIn' = 'signedOut';

jest.mock('@/auth/auth-api', () => ({
  confirmIdentityLink: (token: string) => mockConfirmLink(token),
}));

jest.mock('@/auth/auth-context', () => ({
  useAuth: () => ({ status: mockStatus }),
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
    'link-provider-confirm': require('../link-provider-confirm').default,
    '(auth)/sign-in': stub('sign-in screen'),
    '(app)/index': stub('app home'),
  };
}

function mount(initialUrl: string) {
  return renderRouter(routes(), { initialUrl, wrapper: Providers });
}

beforeEach(() => {
  mockConfirmLink.mockReset();
  mockConfirmLink.mockResolvedValue(undefined);
  mockStatus = 'signedOut';
});

describe('link-provider-confirm screen', () => {
  it('confirms the ?token= on mount and says the sign-in method is linked', async () => {
    const router = mount('/link-provider-confirm?token=tok-123');

    await waitFor(() => expect(mockConfirmLink).toHaveBeenCalledWith('tok-123'));
    expect(await screen.findByText('Sign-in method linked')).toBeOnTheScreen();
    expect(screen.getByText('You can now sign in with that provider.')).toBeOnTheScreen();

    fireEvent.press(screen.getByRole('button', { name: 'Continue' }));
    await waitFor(() => expect(router.getPathname()).toBe('/sign-in'));
  });

  it('continues into the app when a session is already active', async () => {
    mockStatus = 'signedIn';
    mount('/link-provider-confirm?token=tok-123');

    await screen.findByText('Sign-in method linked');
    fireEvent.press(screen.getByRole('button', { name: 'Continue' }));
    await waitFor(() => expect(screen.getByText('app home')).toBeOnTheScreen());
  });

  it('waits for the launch probe before confirming', async () => {
    mockStatus = 'loading';
    mount('/link-provider-confirm?token=tok-123');

    expect(await screen.findByText('Linking your account…')).toBeOnTheScreen();
    expect(mockConfirmLink).not.toHaveBeenCalled();
  });

  it('400 → invalid-link state, pointing back to sign-in for a new link', async () => {
    mockConfirmLink.mockRejectedValue(new AuthApiError({ kind: 'invalid-token' }, 400));
    const router = mount('/link-provider-confirm?token=stale');

    expect(await screen.findByText('This link is invalid or expired')).toBeOnTheScreen();
    expect(
      screen.getByText('Sign in with the provider again to get a new link.'),
    ).toBeOnTheScreen();

    fireEvent.press(screen.getByRole('button', { name: 'Back to sign in' }));
    await waitFor(() => expect(router.getPathname()).toBe('/sign-in'));
  });

  it('409 → the account got another provider meanwhile, and names it', async () => {
    mockConfirmLink.mockRejectedValue(
      new AuthApiError({ kind: 'oauth-email-linked-elsewhere', linkedProvider: 'apple' }, 409),
    );
    mount('/link-provider-confirm?token=tok-123');

    expect(await screen.findByText('Already linked')).toBeOnTheScreen();
    expect(
      screen.getByText('This email is already linked to Apple. Sign in with Apple instead.'),
    ).toBeOnTheScreen();
  });

  it('missing token → invalid-link state, no confirm call', async () => {
    mount('/link-provider-confirm');

    expect(await screen.findByText('This link is missing its token.')).toBeOnTheScreen();
    expect(mockConfirmLink).not.toHaveBeenCalled();
  });
});
