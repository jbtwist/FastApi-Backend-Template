import { DarkTheme, DefaultTheme, Slot, ThemeProvider } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';

import { AnimatedSplashOverlay } from '@/components/animated-icon';
import { AuthProvider, useAuth } from '@/auth/auth-context';
import { LocaleProvider } from '@/i18n/provider';
import { ColorSchemeProvider, useActiveColorScheme } from '@/theme/provider';

SplashScreen.preventAutoHideAsync();

/** Withholds the navigator until the launch probe settles; the overlay keeps
 *  the splash on screen meanwhile. */
function RootNavigator() {
  const { status } = useAuth();
  return (
    <>
      <AnimatedSplashOverlay />
      {status === 'loading' ? null : <Slot />}
    </>
  );
}

/** Inside the provider, so navigation chrome follows the override too. */
function NavigationTheme({ children }: { children: React.ReactNode }) {
  const scheme = useActiveColorScheme();
  return (
    <ThemeProvider value={scheme === 'dark' ? DarkTheme : DefaultTheme}>{children}</ThemeProvider>
  );
}

export default function RootLayout() {
  return (
    <LocaleProvider>
      <ColorSchemeProvider>
        <NavigationTheme>
          <AuthProvider>
            <RootNavigator />
          </AuthProvider>
        </NavigationTheme>
      </ColorSchemeProvider>
    </LocaleProvider>
  );
}
