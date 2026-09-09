import AsyncStorage from '@react-native-async-storage/async-storage';
import { StyleSheet, Text } from 'react-native';

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

const background = () => screen.getByTestId('probe').props.children;
const toggle = () => fireEvent.press(screen.getByTestId('theme-switcher'));

describe('<ThemeSwitcher />', () => {
  beforeEach(async () => {
    await AsyncStorage.clear();
    mockDeviceScheme = 'light';
  });

  it('is a single icon button, not a pair of labelled options', () => {
    renderWithProviders(<ThemeSwitcher />);

    expect(screen.getByTestId('theme-switcher')).toBeOnTheScreen();
    expect(screen.queryByText('Light')).toBeNull();
    expect(screen.queryByText('Dark')).toBeNull();
    expect(screen.queryAllByRole('radio')).toHaveLength(0);
  });

  it('shows the sun while the light palette is active and the moon while dark is', async () => {
    renderWithProviders(<ThemeSwitcher />);

    expect(screen.getByTestId('theme-switcher-icon-light')).toBeOnTheScreen();
    expect(screen.queryByTestId('theme-switcher-icon-dark')).toBeNull();

    toggle();

    await waitFor(() => expect(screen.getByTestId('theme-switcher-icon-dark')).toBeOnTheScreen());
    expect(screen.queryByTestId('theme-switcher-icon-light')).toBeNull();
  });

  it('names the action it will perform, not the state it is in', () => {
    renderWithProviders(<ThemeSwitcher />);

    const button = screen.getByTestId('theme-switcher');
    expect(button.props.accessibilityLabel).toBe('Switch to dark theme');
    expect(button.props.accessibilityState).toMatchObject({ checked: false });

    toggle();

    expect(screen.getByTestId('theme-switcher').props.accessibilityLabel).toBe(
      'Switch to light theme',
    );
    expect(screen.getByTestId('theme-switcher').props.accessibilityState).toMatchObject({
      checked: true,
    });
  });

  it('repaints on press, and back again on a second press', async () => {
    renderWithProviders(
      <>
        <ThemeSwitcher />
        <Probe />
      </>,
    );
    expect(background()).toBe(Colors.light.background);

    toggle();
    await waitFor(() => expect(background()).toBe(Colors.dark.background));

    toggle();
    await waitFor(() => expect(background()).toBe(Colors.light.background));
  });

  it('persists the choice so the next launch keeps it', async () => {
    renderWithProviders(<ThemeSwitcher />);

    toggle();

    await waitFor(async () =>
      expect(await AsyncStorage.getItem(COLOR_SCHEME_STORAGE_KEY)).toBe('dark'),
    );
  });

  it('starts from the device scheme, without having stored a choice', async () => {
    mockDeviceScheme = 'dark';
    renderWithProviders(<ThemeSwitcher />);

    expect(screen.getByTestId('theme-switcher-icon-dark')).toBeOnTheScreen();
    // Reflecting the device is not the same as having chosen it.
    expect(await AsyncStorage.getItem(COLOR_SCHEME_STORAGE_KEY)).toBeNull();
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

    toggle();
    await waitFor(() => expect(background()).toBe(Colors.dark.background));

    mockDeviceScheme = 'light';
    rerender(ui);

    expect(background()).toBe(Colors.dark.background);
  });

  it('tints on hover and clears when the cursor leaves', () => {
    renderWithProviders(<ThemeSwitcher />);
    const button = screen.getByTestId('theme-switcher');
    const fill = () => StyleSheet.flatten(button.props.style).backgroundColor;

    expect(fill()).toBeUndefined();

    fireEvent(button, 'hoverIn');
    expect(fill()).toBe(Colors.light.backgroundElement);

    fireEvent(button, 'hoverOut');
    expect(fill()).toBeUndefined();
  });
});
