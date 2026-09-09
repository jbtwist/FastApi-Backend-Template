import AsyncStorage from '@react-native-async-storage/async-storage';
import { Text } from 'react-native';

import { LOCALE_STORAGE_KEY } from '@/i18n/config';
import { useTranslation } from '@/i18n/provider';
import { fireEvent, renderWithProviders, screen, waitFor } from '@/test-utils';

import { LanguageSwitcher } from '../language-switcher';

/** Renders a translated string so a locale switch is observable, not just stateful. */
function Probe() {
  const { t } = useTranslation();
  return <Text>{t('common.language')}</Text>;
}

describe('<LanguageSwitcher />', () => {
  beforeEach(async () => {
    await AsyncStorage.clear();
  });

  it('offers every supported locale by its own name, with the active one checked', () => {
    renderWithProviders(<LanguageSwitcher />);

    expect(screen.getByRole('radio', { name: 'English' }).props.accessibilityState).toMatchObject({
      checked: true,
    });
    expect(screen.getByRole('radio', { name: 'Español' }).props.accessibilityState).toMatchObject({
      checked: false,
    });
  });

  it('switches the rendered language on press', async () => {
    renderWithProviders(
      <>
        <LanguageSwitcher />
        <Probe />
      </>,
    );
    expect(screen.getByText('Language')).toBeOnTheScreen();

    fireEvent.press(screen.getByRole('radio', { name: 'Español' }));

    expect(screen.getByText('Idioma')).toBeOnTheScreen();
    await waitFor(() =>
      expect(screen.getByRole('radio', { name: 'Español' }).props.accessibilityState).toMatchObject(
        { checked: true },
      ),
    );
  });

  it('persists the choice so the next launch keeps it', async () => {
    renderWithProviders(<LanguageSwitcher />);

    fireEvent.press(screen.getByRole('radio', { name: 'Español' }));

    await waitFor(async () =>
      expect(await AsyncStorage.getItem(LOCALE_STORAGE_KEY)).toBe('es'),
    );
  });

  it('labels the group for assistive tech', () => {
    renderWithProviders(<LanguageSwitcher />);

    expect(screen.getByTestId('language-switcher').props.accessibilityLabel).toBe('Language');
  });
});
