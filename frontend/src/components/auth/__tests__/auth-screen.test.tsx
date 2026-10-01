import { Platform, StyleSheet, Text } from 'react-native';

import { renderWithProviders, screen } from '@/test-utils';

import { AuthScreen } from '../auth-screen';

const originalOS = Platform.OS;
function setPlatform(os: typeof Platform.OS) {
  Object.defineProperty(Platform, 'OS', { configurable: true, get: () => os });
}

afterEach(() => {
  setPlatform(originalOS);
});

describe('<AuthScreen />', () => {
  it('renders the brand, title, subtitle and children', () => {
    renderWithProviders(
      <AuthScreen title="Sign in" subtitle="Welcome back">
        <Text>form body</Text>
      </AuthScreen>,
    );

    expect(screen.getByText('Backend Template')).toBeOnTheScreen();
    expect(screen.getByText('Sign in')).toBeOnTheScreen();
    expect(screen.getByText('Welcome back')).toBeOnTheScreen();
    expect(screen.getByText('form body')).toBeOnTheScreen();
  });

  it('omits the subtitle node when none is given', () => {
    renderWithProviders(
      <AuthScreen title="Sign in">
        <Text>body</Text>
      </AuthScreen>,
    );

    expect(screen.queryByText('Welcome back')).toBeNull();
  });

  it('caps the card at MaxContentWidth', () => {
    renderWithProviders(
      <AuthScreen title="Sign in">
        <Text>body</Text>
      </AuthScreen>,
    );

    const flat = StyleSheet.flatten(screen.getByTestId('auth-screen-card').props.style);
    expect(flat.maxWidth).toBe(800);
  });

  it('draws the "or" divider only when a dividerSlot is passed', () => {
    const { rerender } = renderWithProviders(
      <AuthScreen title="Sign in">
        <Text>body</Text>
      </AuthScreen>,
    );
    expect(screen.queryByTestId('auth-screen-divider')).toBeNull();

    rerender(
      <AuthScreen title="Sign in" dividerSlot={<Text>providers</Text>}>
        <Text>body</Text>
      </AuthScreen>,
    );
    expect(screen.getByTestId('auth-screen-divider')).toBeOnTheScreen();
    expect(screen.getByText('or')).toBeOnTheScreen();
    expect(screen.getByText('providers')).toBeOnTheScreen();
  });

  it('shows the language switcher on web only — native follows the device', () => {
    setPlatform('ios');
    const { rerender } = renderWithProviders(
      <AuthScreen title="Sign in">
        <Text>body</Text>
      </AuthScreen>,
    );
    expect(screen.queryByTestId('language-switcher')).toBeNull();

    setPlatform('web');
    rerender(
      <AuthScreen title="Sign in">
        <Text>body</Text>
      </AuthScreen>,
    );
    expect(screen.getByTestId('language-switcher')).toBeOnTheScreen();
  });

  it('renders the footer slot', () => {
    renderWithProviders(
      <AuthScreen title="Sign in" footer={<Text>cta</Text>}>
        <Text>body</Text>
      </AuthScreen>,
    );

    expect(screen.getByText('cta')).toBeOnTheScreen();
  });
});
