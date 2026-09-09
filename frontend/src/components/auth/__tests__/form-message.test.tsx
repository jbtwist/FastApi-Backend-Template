import AsyncStorage from '@react-native-async-storage/async-storage';

import { en, es } from '@/i18n/locales';
import { fireEvent, renderWithProviders, screen, waitFor } from '@/test-utils';
import { LanguageSwitcher } from '@/components/language-switcher';

import { FormMessage } from '../form-message';

describe('<FormMessage />', () => {
  beforeEach(async () => {
    await AsyncStorage.clear();
  });

  it('renders nothing when there is no message', () => {
    renderWithProviders(<FormMessage message={null} />);

    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('renders an error message as an alert carrying the translated text', () => {
    renderWithProviders(
      <FormMessage message={{ kind: 'error', message: 'errors.invalidCredentials' }} />,
    );

    expect(screen.getByRole('alert')).toHaveTextContent(en.errors.invalidCredentials);
  });

  it('fills placeholders from the message options', () => {
    renderWithProviders(
      <FormMessage
        message={{ kind: 'error', message: { key: 'validation.minLength', options: { min: 12 } } }}
      />,
    );

    expect(screen.getByRole('alert')).toHaveTextContent(/12/);
  });

  it('announces politely for screen readers', () => {
    renderWithProviders(<FormMessage message={{ kind: 'info', message: 'providers.comingSoon' }} />);

    expect(screen.getByRole('alert').props.accessibilityLiveRegion).toBe('polite');
  });

  it('swaps its content when the message changes', () => {
    const { rerender } = renderWithProviders(
      <FormMessage message={{ kind: 'success', message: 'verifyEmail.resendSent' }} />,
    );
    expect(screen.getByRole('alert')).toHaveTextContent(en.verifyEmail.resendSent);

    rerender(<FormMessage message={{ kind: 'error', message: 'errors.unknown' }} />);
    expect(screen.getByRole('alert')).toHaveTextContent(en.errors.unknown);
    expect(screen.queryByText(en.verifyEmail.resendSent)).toBeNull();
  });

  it('follows a language switch while it is on screen', async () => {
    renderWithProviders(
      <>
        <LanguageSwitcher />
        <FormMessage message={{ kind: 'error', message: 'errors.unknown' }} />
      </>,
    );
    expect(screen.getByRole('alert')).toHaveTextContent(en.errors.unknown);

    fireEvent.press(screen.getByRole('radio', { name: 'Español' }));

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent(es.errors.unknown));
  });
});
