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

const mockSignIn = jest.fn<Promise<void>, [string, string]>();
let mockSignedOutReason: 'session-expired' | null = null;

jest.mock('@/auth/auth-context', () => ({
  useAuth: () => ({
    status: 'signedOut',
    user: null,
    signedOutReason: mockSignedOutReason,
    signIn: mockSignIn,
  }),
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
    '(auth)/sign-in': require('../sign-in').default,
    '(auth)/register': stub('register screen'),
    '(auth)/forgot-password': stub('forgot-password screen'),
    '(auth)/verify-email': stub('verify-email screen'),
    '(app)/index': stub('app home'),
  };
}

function mount() {
  return renderRouter(routes(), { initialUrl: '/sign-in', wrapper: Providers });
}

async function fillForm(email: string, password: string) {
  fireEvent.changeText(screen.getByLabelText('Email'), email);
  fireEvent.changeText(screen.getByLabelText('Password'), password);
}

function submit() {
  fireEvent.press(screen.getByRole('button', { name: 'Sign in' }));
}

beforeEach(() => {
  mockSignIn.mockReset();
  mockSignIn.mockResolvedValue(undefined);
  mockSignedOutReason = null;
});

describe('sign-in screen — layout', () => {
  it('renders the email + password fields, the primary button, the links and the provider buttons', async () => {
    mount();

    expect(screen.getByLabelText('Email')).toBeOnTheScreen();
    expect(screen.getByLabelText('Password')).toBeOnTheScreen();
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeOnTheScreen();
    expect(screen.getByText('Create an account')).toBeOnTheScreen();
    expect(screen.getByText('Forgot password?')).toBeOnTheScreen();
    expect(screen.getByTestId('provider-buttons')).toBeOnTheScreen();
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
