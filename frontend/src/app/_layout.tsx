import { DarkTheme, DefaultTheme, Slot, ThemeProvider } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { useColorScheme } from 'react-native';

import { AnimatedSplashOverlay } from '@/components/animated-icon';
import { AuthProvider, useAuth } from '@/auth/auth-context';
import { LocaleProvider } from '@/i18n/provider';

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

export default function RootLayout() {
  const colorScheme = useColorScheme();
  return (
    <LocaleProvider>
      <ThemeProvider value={colorScheme === 'dark' ? DarkTheme : DefaultTheme}>
        <AuthProvider>
          <RootNavigator />
        </AuthProvider>
      </ThemeProvider>
    </LocaleProvider>
  );
}
