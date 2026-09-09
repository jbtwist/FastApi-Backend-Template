import AsyncStorage from '@react-native-async-storage/async-storage';
import { StyleSheet, Text, View } from 'react-native';
import Svg from 'react-native-svg';

import { Colors } from '@/constants/theme';
import { LOCALE_STORAGE_KEY } from '@/i18n/config';
import { useTranslation } from '@/i18n/provider';
import { fireEvent, renderWithProviders, screen, waitFor } from '@/test-utils';

import { LanguageSwitcher } from '../language-switcher';

/** Renders a translated string so a locale switch is observable, not just stateful. */
function Probe() {
  const { t } = useTranslation();
  return <Text>{t('common.language')}</Text>;
}

const open = () => fireEvent.press(screen.getByTestId('language-switcher'));

// The trigger is measured to place the list under it. The test renderer has no
// layout, so `measureInWindow` never fires its callback on its own.
const TRIGGER_BOX = { x: 260, y: 40, width: 120, height: 28 };

beforeAll(() => {
  jest
    .spyOn(View.prototype, 'measureInWindow')
    .mockImplementation((callback: (...box: number[]) => void) => {
      callback(TRIGGER_BOX.x, TRIGGER_BOX.y, TRIGGER_BOX.width, TRIGGER_BOX.height);
    });
});

afterAll(() => jest.restoreAllMocks());

describe('<LanguageSwitcher />', () => {
  beforeEach(async () => {
    await AsyncStorage.clear();
  });

  it('shows the active language on the trigger, with the list closed', () => {
    renderWithProviders(<LanguageSwitcher />);

    const trigger = screen.getByTestId('language-switcher');
    expect(trigger.props.accessibilityValue).toMatchObject({ text: 'English' });
    expect(trigger.props.accessibilityState).toMatchObject({ expanded: false });
    expect(screen.queryByTestId('language-switcher-list')).toBeNull();
  });

  it('lists every supported locale by its own name once opened', () => {
    renderWithProviders(<LanguageSwitcher />);

    open();

    expect(screen.getByTestId('language-switcher-list')).toBeOnTheScreen();
    expect(screen.getByRole('radio', { name: 'English' }).props.accessibilityState).toMatchObject({
      checked: true,
    });
    expect(screen.getByRole('radio', { name: 'Español' }).props.accessibilityState).toMatchObject({
      checked: false,
    });
  });

  it('switches the rendered language and closes the list on choose', async () => {
    renderWithProviders(
      <>
        <LanguageSwitcher />
        <Probe />
      </>,
    );
    expect(screen.getByText('Language')).toBeOnTheScreen();

    open();
    fireEvent.press(screen.getByRole('radio', { name: 'Español' }));

    expect(screen.getByText('Idioma')).toBeOnTheScreen();
    await waitFor(() => expect(screen.queryByTestId('language-switcher-list')).toBeNull());
  });

  it('persists the choice so the next launch keeps it', async () => {
    renderWithProviders(<LanguageSwitcher />);

    open();
    fireEvent.press(screen.getByRole('radio', { name: 'Español' }));

    await waitFor(async () => expect(await AsyncStorage.getItem(LOCALE_STORAGE_KEY)).toBe('es'));
  });

  it('toggles shut on a second press, changing nothing', async () => {
    renderWithProviders(<LanguageSwitcher />);

    open();
    expect(screen.getByTestId('language-switcher-list')).toBeOnTheScreen();

    open();

    await waitFor(() => expect(screen.queryByTestId('language-switcher-list')).toBeNull());
    expect(await AsyncStorage.getItem(LOCALE_STORAGE_KEY)).toBeNull();
  });

  it('positions the list directly under the trigger, not centred on screen', () => {
    renderWithProviders(<LanguageSwitcher />);
    open();

    const style = StyleSheet.flatten(screen.getByTestId('language-switcher-list').props.style);
    expect(style).toMatchObject({
      position: 'absolute',
      top: TRIGGER_BOX.y + TRIGGER_BOX.height + 4,
    });
    // Right edge lines up with the trigger's.
    expect(style.left + style.width).toBe(TRIGGER_BOX.x + TRIGGER_BOX.width);
  });

  it('closes without changing anything when the outside is pressed', async () => {
    renderWithProviders(<LanguageSwitcher />);

    open();
    fireEvent.press(screen.getByTestId('language-switcher-backdrop'));

    await waitFor(() => expect(screen.queryByTestId('language-switcher-list')).toBeNull());
    expect(await AsyncStorage.getItem(LOCALE_STORAGE_KEY)).toBeNull();
  });

  it('highlights the row under the cursor, and clears it when the cursor leaves', () => {
    renderWithProviders(<LanguageSwitcher />);
    open();

    const row = screen.getByRole('radio', { name: 'Español' });
    const background = () => StyleSheet.flatten(row.props.style).backgroundColor;

    expect(background()).toBeUndefined();

    fireEvent(row, 'hoverIn');
    expect(background()).toBe(Colors.light.backgroundElement);

    fireEvent(row, 'hoverOut');
    expect(background()).toBeUndefined();
  });

  it('leaves the active row on its selected colour while hovered', () => {
    renderWithProviders(<LanguageSwitcher />);
    open();

    const active = screen.getByRole('radio', { name: 'English' });
    fireEvent(active, 'hoverIn');

    expect(StyleSheet.flatten(active.props.style).backgroundColor).toBe(
      Colors.light.backgroundSelected,
    );
  });

  it('renders a flag alongside each language, hidden from assistive tech', () => {
    renderWithProviders(<LanguageSwitcher />);
    open();

    // The flag is decorative; the row is labelled by the language name alone.
    expect(screen.getByRole('radio', { name: 'Español' }).props.accessibilityLabel).toBe('Español');
    expect(screen.UNSAFE_getAllByType(Svg).length).toBeGreaterThan(0);
  });

  it('labels the trigger and the list for assistive tech', () => {
    renderWithProviders(<LanguageSwitcher />);

    expect(screen.getByTestId('language-switcher').props.accessibilityLabel).toBe('Language');

    open();
    expect(screen.getByTestId('language-switcher-list').props.accessibilityLabel).toBe('Language');
  });
});
