import AsyncStorage from '@react-native-async-storage/async-storage';
import { Text } from 'react-native';

import { Colors } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import { COLOR_SCHEME_STORAGE_KEY } from '@/theme/config';
import { fireEvent, renderWithProviders, screen, waitFor } from '@/test-utils';

import { ThemeSwitcher } from '../theme-switcher';

// jest-expo pins react-native's `useColorScheme` to light, so the device
// setting is driven through the app's own wrapper instead.
let mockDeviceScheme: 'light' | 'dark' = 'light';
jest.mock('@/hooks/use-color-scheme', () => ({
  useColorScheme: () => mockDeviceScheme,
}));

/** Renders the active background so a scheme change is observable, not just stored. */
function Probe() {
  return <Text testID="probe">{useTheme().background}</Text>;
}

function background() {
  return screen.getByTestId('probe').props.children;
}

describe('<ThemeSwitcher />', () => {
  beforeEach(async () => {
    await AsyncStorage.clear();
    mockDeviceScheme = 'light';
  });

  it('offers light and dark only — never a "system" option', () => {
    renderWithProviders(<ThemeSwitcher />);

    expect(screen.getAllByRole('radio')).toHaveLength(2);
    expect(screen.getByRole('radio', { name: 'Light' })).toBeOnTheScreen();
    expect(screen.getByRole('radio', { name: 'Dark' })).toBeOnTheScreen();
    expect(screen.queryByRole('radio', { name: /system/i })).toBeNull();
  });

  it('marks the device scheme as selected before any choice is made', async () => {
    mockDeviceScheme = 'dark';
    renderWithProviders(<ThemeSwitcher />);

    expect(screen.getByRole('radio', { name: 'Dark' }).props.accessibilityState).toMatchObject({
      checked: true,
    });
    // Reflecting the device is not the same as having chosen it.
    expect(await AsyncStorage.getItem(COLOR_SCHEME_STORAGE_KEY)).toBeNull();
  });

  it('repaints on press', async () => {
    renderWithProviders(
      <>
        <ThemeSwitcher />
        <Probe />
      </>,
    );
    expect(background()).toBe(Colors.light.background);

    fireEvent.press(screen.getByRole('radio', { name: 'Dark' }));

    await waitFor(() => expect(background()).toBe(Colors.dark.background));
  });

  it('persists the choice so the next launch keeps it', async () => {
    renderWithProviders(<ThemeSwitcher />);

    fireEvent.press(screen.getByRole('radio', { name: 'Dark' }));

    await waitFor(async () =>
      expect(await AsyncStorage.getItem(COLOR_SCHEME_STORAGE_KEY)).toBe('dark'),
    );
  });

  it('restores a stored choice over the device setting', async () => {
    await AsyncStorage.setItem(COLOR_SCHEME_STORAGE_KEY, 'dark');
    renderWithProviders(
      <>
        <ThemeSwitcher />
        <Probe />
      </>,
    );

    await waitFor(() => expect(background()).toBe(Colors.dark.background));
  });

  it('keeps following the device while no choice is stored', () => {
    const { rerender } = renderWithProviders(<Probe />);
    expect(background()).toBe(Colors.light.background);

    mockDeviceScheme = 'dark';
    rerender(<Probe />);

    expect(background()).toBe(Colors.dark.background);
  });

  it('stops following the device once a choice is made', async () => {
    const ui = (
      <>
        <ThemeSwitcher />
        <Probe />
      </>
    );
    const { rerender } = renderWithProviders(ui);

    fireEvent.press(screen.getByRole('radio', { name: 'Dark' }));
    await waitFor(() => expect(background()).toBe(Colors.dark.background));

    mockDeviceScheme = 'light';
    rerender(ui);

    expect(background()).toBe(Colors.dark.background);
  });

  it('labels the group for assistive tech', () => {
    renderWithProviders(<ThemeSwitcher />);

    expect(screen.getByTestId('theme-switcher').props.accessibilityLabel).toBe('Theme');
  });
});
