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
import { DEFAULT_LOCALE, i18n } from '@/i18n';
import { LOCALE_STORAGE_KEY } from '@/i18n/config';
import { LocaleProvider, useLocale } from '@/i18n/provider';

const mockRegister = jest.fn<Promise<void>, [string, string]>();
const mockSetPending = jest.fn<Promise<void>, [unknown]>();

jest.mock('@/auth/auth-context', () => ({
  useAuth: () => ({ status: 'signedOut', user: null, register: mockRegister }),
}));

jest.mock('@/auth/pending-verification', () => ({
  set: (value: unknown) => mockSetPending(value),
  get: jest.fn().mockResolvedValue(null),
  clear: jest.fn().mockResolvedValue(undefined),
}));

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
        {children}
        <LocaleProbe />
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
    '(auth)/register': require('../register').default,
    '(auth)/sign-in': stub('sign-in screen'),
    '(auth)/verify-email': stub('verify-email screen'),
  };
}

function mount() {
  return renderRouter(routes(), { initialUrl: '/register', wrapper: Providers });
}

async function fillForm(email: string, password: string) {
  fireEvent.changeText(screen.getByLabelText('Email'), email);
  fireEvent.changeText(screen.getByLabelText('Password'), password);
}

function submit() {
  fireEvent.press(screen.getByRole('button', { name: 'Create account' }));
}

beforeEach(async () => {
  await AsyncStorage.clear();
  i18n.locale = DEFAULT_LOCALE;
  mockRegister.mockReset();
  mockRegister.mockResolvedValue(undefined);
  mockSetPending.mockReset();
  mockSetPending.mockResolvedValue(undefined);
});

describe('register screen — layout', () => {
  it('renders the fields, the password rule hint, the sign-in link and the provider buttons', () => {
    mount();

    expect(screen.getByLabelText('Email')).toBeOnTheScreen();
    expect(screen.getByLabelText('Password')).toBeOnTheScreen();
    expect(screen.getByRole('button', { name: 'Create account' })).toBeOnTheScreen();
    expect(
      screen.getByText('At least 12 characters. Common or breached passwords are rejected.'),
    ).toBeOnTheScreen();
    expect(screen.getByText('Already have an account? Sign in')).toBeOnTheScreen();
    expect(screen.getByTestId('provider-buttons')).toBeOnTheScreen();
  });

  it('routes to sign-in from the link', async () => {
    const router = mount();

    fireEvent.press(screen.getByText('Already have an account? Sign in'));
    await waitFor(() => expect(router.getPathname()).toBe('/sign-in'));
  });
});

describe('register screen — client validation', () => {
  it('blocks submit and shows inline messages when both fields are empty', async () => {
    mount();

    submit();

    await waitFor(() =>
      expect(screen.getAllByText('This field is required.').length).toBe(2),
    );
    expect(mockRegister).not.toHaveBeenCalled();
  });

  it('blocks submit on an invalid email', async () => {
    mount();

    await fillForm('nope', 'a-strong-password');
    submit();

    await waitFor(() =>
      expect(screen.getByText('Enter a valid email address.')).toBeOnTheScreen(),
    );
    expect(mockRegister).not.toHaveBeenCalled();
  });

  it('blocks submit on a password shorter than the policy minimum', async () => {
    mount();

    await fillForm('user@example.com', 'short');
    submit();

    await waitFor(() =>
      expect(screen.getByText('Must be at least 12 characters.')).toBeOnTheScreen(),
    );
    expect(mockRegister).not.toHaveBeenCalled();
  });

  it('blocks submit on a password longer than the policy maximum', async () => {
    mount();

    await fillForm('user@example.com', 'a'.repeat(129));
    submit();

    await waitFor(() =>
      expect(screen.getByText('Must be at most 128 characters.')).toBeOnTheScreen(),
    );
    expect(mockRegister).not.toHaveBeenCalled();
  });
});

describe('register screen — submission', () => {
  it('registers, stores the pending-verification record and navigates to verify-email', async () => {
    const router = mount();

    await fillForm('new@example.com', 'a-strong-password');
    await act(async () => {
      submit();
    });

    expect(mockRegister).toHaveBeenCalledWith('new@example.com', 'a-strong-password');
    expect(mockSetPending).toHaveBeenCalledWith(
      expect.objectContaining({ email: 'new@example.com', lastSentAt: expect.any(Number) }),
    );
    await waitFor(() => expect(router.getPathname()).toBe('/verify-email'));
  });

  it('always lands on verify-email — no branch on an already-registered address', async () => {
    // The server returns the same 204 whether or not the email exists; the
    // screen must not surface anything that distinguishes the two.
    const router = mount();

    await fillForm('taken@example.com', 'a-strong-password');
    await act(async () => {
      submit();
    });

    await waitFor(() => expect(router.getPathname()).toBe('/verify-email'));
    expect(screen.queryByTestId('register-form-message')).toBeNull();
  });

  it('422 → shows the screen\'s own breached-password copy on the password field', async () => {
    mockRegister.mockRejectedValue(new AuthApiError({ kind: 'password-policy' }, 422));

    const router = mount();
    await fillForm('new@example.com', 'a-strong-password');
    await act(async () => {
      submit();
    });

    await waitFor(() =>
      expect(
        screen.getByText('This password has appeared in a data breach. Choose a different one.'),
      ).toBeOnTheScreen(),
    );
    expect(router.getPathname()).toBe('/register');
  });

  it('422 on the email → the message goes on the email field, not the password one', async () => {
    mockRegister.mockRejectedValue(new AuthApiError({ kind: 'invalid-email' }, 422));

    const router = mount();
    await fillForm('someone@nope.invalid', 'a-strong-password');
    await act(async () => {
      submit();
    });

    await waitFor(() =>
      expect(screen.getByText('Enter a valid email address.')).toBeOnTheScreen(),
    );
    expect(screen.queryByTestId('register-form-message')).toBeNull();
    expect(router.getPathname()).toBe('/register');
  });

  it('429 → rate-limited banner', async () => {
    mockRegister.mockRejectedValue(new AuthApiError({ kind: 'rate-limited' }, 429));

    mount();
    await fillForm('new@example.com', 'a-strong-password');
    await act(async () => {
      submit();
    });

    await waitFor(() =>
      expect(
        screen.getByText('Too many attempts. Please try again later.'),
      ).toBeOnTheScreen(),
    );
  });

  it('renders the rejection in the active language, not English', async () => {
    await AsyncStorage.setItem(LOCALE_STORAGE_KEY, 'es');
    mockRegister.mockRejectedValue(new AuthApiError({ kind: 'password-policy' }, 422));

    mount();
    await waitFor(() => expect(screen.getByText('Crear cuenta')).toBeOnTheScreen());

    fireEvent.changeText(screen.getByLabelText('Correo electrónico'), 'new@example.com');
    fireEvent.changeText(screen.getByLabelText('Contraseña'), 'a-strong-password');
    await act(async () => {
      fireEvent.press(screen.getByRole('button', { name: 'Crear cuenta' }));
    });

    await waitFor(() =>
      expect(
        screen.getByText('Esta contraseña ha aparecido en una filtración de datos. Elige otra.'),
      ).toBeOnTheScreen(),
    );
  });

  it('re-translates a message already on screen when the language changes', async () => {
    mockRegister.mockRejectedValue(new AuthApiError({ kind: 'password-policy' }, 422));

    mount();
    await fillForm('new@example.com', 'a-strong-password');
    await act(async () => {
      submit();
    });
    await waitFor(() =>
      expect(
        screen.getByText('This password has appeared in a data breach. Choose a different one.'),
      ).toBeOnTheScreen(),
    );

    await act(async () => {
      fireEvent.press(screen.getByTestId('switch-to-es'));
    });

    await waitFor(() =>
      expect(
        screen.getByText('Esta contraseña ha aparecido en una filtración de datos. Elige otra.'),
      ).toBeOnTheScreen(),
    );
  });

  it('disables the primary button while the request is in flight', async () => {
    let release: () => void = () => {};
    mockRegister.mockReturnValue(
      new Promise<void>((resolve) => {
        release = resolve;
      }),
    );

    mount();
    await fillForm('new@example.com', 'a-strong-password');
    submit();

    await waitFor(() =>
      expect(
        screen.getByRole('button', { name: 'Create account' }).props.accessibilityState,
      ).toMatchObject({ disabled: true }),
    );

    await act(async () => {
      release();
    });
  });
});
