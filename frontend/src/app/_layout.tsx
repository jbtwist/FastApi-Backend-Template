import { DarkTheme, DefaultTheme, Slot, ThemeProvider } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { ActivityIndicator, StyleSheet, View } from 'react-native';

import { AnimatedSplashOverlay } from '@/components/animated-icon';
import { AuthProvider, useAuth } from '@/auth/auth-context';
import { useTheme } from '@/hooks/use-theme';
import { LocaleProvider, useTranslation } from '@/i18n/provider';
import { ColorSchemeProvider, useActiveColorScheme } from '@/theme/provider';

SplashScreen.preventAutoHideAsync();

/** Withholds the navigator until the launch probe settles. The splash overlay
 *  fades on its own schedule, so a slow probe shows a spinner, not a blank screen. */
function RootNavigator() {
  const { status } = useAuth();
  return (
    <>
      <AnimatedSplashOverlay />
      {status === 'loading' ? <LaunchProbePending /> : <Slot />}
    </>
  );
}

function LaunchProbePending() {
  const theme = useTheme();
  const { t } = useTranslation();
  return (
    <View style={[styles.pending, { backgroundColor: theme.background }]}>
      <ActivityIndicator
        size="large"
        color={theme.tint}
        accessibilityLabel={t('common.loading')}
      />
    </View>
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

const styles = StyleSheet.create({
  pending: { flex: 1, alignItems: 'center', justifyContent: 'center' },
});
