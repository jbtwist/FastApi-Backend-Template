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

import AsyncStorage from '@react-native-async-storage/async-storage';

import { AuthApiError } from '@/auth/api-client';
import { mockFetch, type MockFetch } from '@/test-utils';
import { DEFAULT_LOCALE, i18n } from '@/i18n';
import { LocaleProvider, useLocale } from '@/i18n/provider';
import { ColorSchemeProvider } from '@/theme/provider';

const mockSignIn = jest.fn<Promise<void>, [string, string]>();
const mockCompleteOAuthSignIn = jest.fn<Promise<void>, [unknown]>();
let mockSignedOutReason: 'session-expired' | null = null;

jest.mock('@/auth/auth-context', () => ({
  useAuth: () => ({
    status: 'signedOut',
    user: null,
    signedOutReason: mockSignedOutReason,
    signIn: mockSignIn,
    completeOAuthSignIn: mockCompleteOAuthSignIn,
  }),
}));

// The platform SDK is faked at the module edge; the real `oauth-client.ts`
// runs against it and against `fetchMock` below.
const mockPromptAsync = jest.fn();
jest.mock('expo-auth-session', () => ({
  AuthRequest: jest.fn().mockImplementation(() => ({ promptAsync: mockPromptAsync })),
  ResponseType: { IdToken: 'id_token' },
  makeRedirectUri: () => 'com.example.app://redirect',
}));
jest.mock('expo-auth-session/providers/google', () => ({ discovery: {} }));

const SAFE_AREA_METRICS = {
  frame: { x: 0, y: 0, width: 390, height: 844 },
  insets: { top: 47, left: 0, right: 0, bottom: 34 },
};

/**
 * Stands in for `<LanguageSwitcher />`, which renders on web only and so is
 * absent from this native-preset render.
 */
function LocaleProbe() {
  const { setLocale } = useLocale();
  return <Text testID="switch-to-es" onPress={() => void setLocale('es')} />;
}

function Providers({ children }: { children: ReactNode }) {
  return (
    <SafeAreaProvider initialMetrics={SAFE_AREA_METRICS}>
      <LocaleProvider>
        <ColorSchemeProvider>
          {children}
          <LocaleProbe />
        </ColorSchemeProvider>
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
    '(auth)/sign-in': require('../sign-in').default,
    '(auth)/register': stub('register screen'),
    '(auth)/forgot-password': stub('forgot-password screen'),
    '(auth)/verify-email': stub('verify-email screen'),
    '(app)/index': stub('app home'),
  };
}

function mount(initialUrl = '/sign-in') {
  return renderRouter(routes(), { initialUrl, wrapper: Providers });
}

async function fillForm(email: string, password: string) {
  fireEvent.changeText(screen.getByLabelText('Email'), email);
  fireEvent.changeText(screen.getByLabelText('Password'), password);
}

function submit() {
  fireEvent.press(screen.getByRole('button', { name: 'Sign in' }));
}

beforeEach(async () => {
  await AsyncStorage.clear();
  i18n.locale = DEFAULT_LOCALE;
  mockSignIn.mockReset();
  mockSignIn.mockResolvedValue(undefined);
  mockCompleteOAuthSignIn.mockReset();
  mockCompleteOAuthSignIn.mockResolvedValue(undefined);
  mockPromptAsync.mockReset();
  mockSignedOutReason = null;
});

describe('sign-in screen — layout', () => {
  it('renders the email + password fields, the primary button, the links and the provider buttons', async () => {
    // Provider buttons render only once the launch fetch resolves —
    // hide-until-known, never a stale static default.
    const fetchMock = mockFetch().queueJson(200, { providers: ['google'] });
    mount();

    expect(screen.getByLabelText('Email')).toBeOnTheScreen();
    expect(screen.getByLabelText('Password')).toBeOnTheScreen();
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeOnTheScreen();
    expect(screen.getByText('Create an account')).toBeOnTheScreen();
    expect(screen.getByText('Forgot password?')).toBeOnTheScreen();
    await waitFor(() => expect(screen.getByTestId('provider-buttons')).toBeOnTheScreen());
    fetchMock.restore();
  });

  it('navigates to register / forgot-password from the links', async () => {
    const router = mount();

    fireEvent.press(screen.getByText('Create an account'));
    await waitFor(() => expect(router.getPathname()).toBe('/register'));
  });

  it('routes forgot-password to its screen', async () => {
    const router = mount();

    fireEvent.press(screen.getByText('Forgot password?'));
    await waitFor(() => expect(router.getPathname()).toBe('/forgot-password'));
  });
});

describe('sign-in screen — client validation', () => {
  it('blocks submit and shows inline messages when both fields are empty', async () => {
    mount();

    submit();

    await waitFor(() =>
      expect(screen.getAllByText('This field is required.').length).toBe(2),
    );
    expect(mockSignIn).not.toHaveBeenCalled();
  });

  it('blocks submit on an invalid email', async () => {
    mount();

    await fillForm('not-an-email', 'a-password');
    submit();

    await waitFor(() =>
      expect(screen.getByText('Enter a valid email address.')).toBeOnTheScreen(),
    );
    expect(mockSignIn).not.toHaveBeenCalled();
  });

  it('blocks submit on an empty password', async () => {
    mount();

    await fillForm('user@example.com', '');
    submit();

    await waitFor(() =>
      expect(screen.getByText('This field is required.')).toBeOnTheScreen(),
    );
    expect(mockSignIn).not.toHaveBeenCalled();
  });
});

describe('sign-in screen — submission', () => {
  it('calls signIn with the entered credentials and routes into the app on success', async () => {
    mount();

    await fillForm('user@example.com', 'correct horse');
    await act(async () => {
      submit();
    });

    expect(mockSignIn).toHaveBeenCalledWith('user@example.com', 'correct horse');
    await waitFor(() => expect(screen.getByText('app home')).toBeOnTheScreen());
  });

  it('disables the primary button while the request is in flight', async () => {
    let release: () => void = () => {};
    mockSignIn.mockReturnValue(
      new Promise<void>((resolve) => {
        release = resolve;
      }),
    );

    mount();
    await fillForm('user@example.com', 'correct horse');
    submit();

    await waitFor(() =>
      expect(
        screen.getByRole('button', { name: 'Sign in' }).props.accessibilityState,
      ).toMatchObject({ disabled: true }),
    );

    await act(async () => {
      release();
    });
  });

  it('401 → combined error, password cleared, email kept', async () => {
    mockSignIn.mockRejectedValue(new AuthApiError({ kind: 'invalid-credentials' }, 401));

    mount();
    await fillForm('user@example.com', 'wrong-password');
    await act(async () => {
      submit();
    });

    await waitFor(() =>
      expect(screen.getByText('Email or password is incorrect.')).toBeOnTheScreen(),
    );
    expect(screen.getByLabelText('Email').props.value).toBe('user@example.com');
    expect(screen.getByLabelText('Password').props.value).toBe('');
  });

  it('403 → replaces to /verify-email carrying the email', async () => {
    mockSignIn.mockRejectedValue(
      new AuthApiError({ kind: 'email-not-verified', email: 'user@example.com' }, 403),
    );

    const router = mount();
    await fillForm('user@example.com', 'correct horse');
    await act(async () => {
      submit();
    });

    await waitFor(() => expect(router.getPathname()).toBe('/verify-email'));
    expect(router.getSearchParams()).toMatchObject({ email: 'user@example.com' });
  });

  it('429 → rate-limited message', async () => {
    mockSignIn.mockRejectedValue(new AuthApiError({ kind: 'rate-limited' }, 429));

    mount();
    await fillForm('user@example.com', 'correct horse');
    await act(async () => {
      submit();
    });

    await waitFor(() =>
      expect(
        screen.getByText('Too many attempts. Please try again later.'),
      ).toBeOnTheScreen(),
    );
  });

  it('unexpected failure → generic error', async () => {
    mockSignIn.mockRejectedValue(new Error('boom'));

    mount();
    await fillForm('user@example.com', 'correct horse');
    await act(async () => {
      submit();
    });

    await waitFor(() =>
      expect(
        screen.getByText('Something went wrong. Please try again later.'),
      ).toBeOnTheScreen(),
    );
  });
});

describe('sign-in screen — signed-out notice', () => {
  it('shows the "please sign in again" notice when a signedOutReason is present', async () => {
    mockSignedOutReason = 'session-expired';
    mount();

    expect(screen.getByText('Please sign in again.')).toBeOnTheScreen();
  });

  it('shows no notice when there is no signedOutReason', async () => {
    mount();

    expect(screen.queryByText('Please sign in again.')).toBeNull();
  });
});

describe('sign-in screen — oauth (native)', () => {
  let fetchMock: MockFetch;

  beforeEach(() => {
    fetchMock = mockFetch();
  });

  afterEach(() => {
    fetchMock.restore();
  });

  it('pressing a provider button reaches the authenticated area', async () => {
    fetchMock
      .queueJson(200, { providers: ['google'] }) // GET /auth/oauth/providers, on launch
      .queueJson(200, { state: 's1', nonce: 'n1', expires_in: 600 }) // POST /start
      .queueJson(200, {
        id: 'u1',
        email: 'user@example.com',
        email_verified: true,
        access_token: 'a',
        refresh_token: 'r',
        token_type: 'bearer',
      }); // POST /native
    mockPromptAsync.mockResolvedValue({
      type: 'success',
      params: { id_token: 'id-token-1' },
      authentication: { idToken: 'id-token-1' },
      url: 'com.example.app://redirect',
    });

    mount();
    await waitFor(() => expect(screen.getByTestId('provider-button-google')).toBeOnTheScreen());

    await act(async () => {
      fireEvent.press(screen.getByRole('button', { name: 'Continue with Google' }));
    });

    await waitFor(() => expect(mockCompleteOAuthSignIn).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByText('app home')).toBeOnTheScreen());
  });

  it('cancelling the provider sheet returns quietly, with no error banner', async () => {
    fetchMock
      .queueJson(200, { providers: ['google'] })
      .queueJson(200, { state: 's1', nonce: 'n1', expires_in: 600 });
    mockPromptAsync.mockResolvedValue({ type: 'cancel' });

    mount();
    await waitFor(() => expect(screen.getByTestId('provider-button-google')).toBeOnTheScreen());

    await act(async () => {
      fireEvent.press(screen.getByRole('button', { name: 'Continue with Google' }));
    });

    await waitFor(() => expect(mockPromptAsync).toHaveBeenCalled());
    expect(mockCompleteOAuthSignIn).not.toHaveBeenCalled();
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('a provider absent from GET /auth/oauth/providers is hidden, not disabled', async () => {
    // The server, not the static `authConfig.providers` default, decides what
    // renders: an empty list must hide Google too, proving this isn't just
    // today's hardcoded default happening to agree with the assertion.
    fetchMock.queueJson(200, { providers: [] });

    mount();

    await waitFor(() => expect(screen.queryByTestId('provider-buttons')).toBeNull());
  });

  it('an on-screen provider error follows a language switch', async () => {
    fetchMock
      .queueJson(200, { providers: ['google'] })
      .queueJson(200, { state: 's1', nonce: 'n1', expires_in: 600 })
      .queueJson(403, { detail: 'email_not_verified_by_provider' });
    mockPromptAsync.mockResolvedValue({
      type: 'success',
      params: { id_token: 'id-token-1' },
      authentication: { idToken: 'id-token-1' },
      url: 'com.example.app://redirect',
    });

    mount();
    await waitFor(() => expect(screen.getByTestId('provider-button-google')).toBeOnTheScreen());

    await act(async () => {
      fireEvent.press(screen.getByRole('button', { name: 'Continue with Google' }));
    });

    await waitFor(() =>
      expect(
        screen.getByText("Google couldn't confirm your email. Create an account with it instead."),
      ).toBeOnTheScreen(),
    );

    await act(async () => {
      fireEvent.press(screen.getByTestId('switch-to-es'));
    });

    await waitFor(() =>
      expect(
        screen.getByText(
          'Google no pudo confirmar tu correo electrónico. Crea una cuenta con él en su lugar.',
        ),
      ).toBeOnTheScreen(),
    );
  });
});

describe('sign-in screen — oauth web return', () => {
  let fetchMock: MockFetch;

  beforeEach(() => {
    fetchMock = mockFetch().queueJson(200, { providers: ['google'] });
  });

  afterEach(() => {
    fetchMock.restore();
  });

  it('email_not_verified_by_provider shows the "couldn\'t confirm your address" state, and clears the flag', async () => {
    const router = mount('/sign-in?oauth_error=email_not_verified_by_provider');

    await waitFor(() =>
      expect(
        screen.getByText("Google couldn't confirm your email. Create an account with it instead."),
      ).toBeOnTheScreen(),
    );
    await waitFor(() => expect(router.getSearchParams()).toEqual({}));
  });

  it('cancelled shows no banner at all, and clears the flag', async () => {
    const router = mount('/sign-in?oauth_error=cancelled');

    expect(screen.queryByRole('alert')).toBeNull();
    await waitFor(() => expect(router.getSearchParams()).toEqual({}));
  });
});
