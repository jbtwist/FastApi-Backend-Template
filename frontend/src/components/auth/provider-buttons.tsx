/**
 * Third-party sign-in buttons — one per configured provider.
 *
 * Google mandates its own button appearance (colour, wordmark, minimum
 * size) — see https://developers.google.com/identity/branding-guidelines —
 * so its button ignores the app's own palette and picks a light/dark variant
 * off the active colour scheme instead, for contrast. Every other provider
 * (currently just `apple`, unwired — 2026-09-12) keeps the app's generic
 * themed style.
 */
import { useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import Svg, { Path } from 'react-native-svg';

import { ThemedText } from '@/components/themed-text';
import { authConfig, type OAuthProvider } from '@/auth/config';
import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import { useActiveColorScheme } from '@/theme/provider';
import { useTranslation } from '@/i18n/provider';

import { FormMessage, type FormMessageValue } from './form-message';

export type ProviderButtonsProps = {
  /** Providers to show, in order. Defaults to `authConfig.providers`. */
  providers?: OAuthProvider[];
  enabled?: boolean;
  onSelect?: (provider: OAuthProvider) => void;
};

export const PROVIDER_LABEL_KEY: Record<OAuthProvider, 'providers.google' | 'providers.apple'> = {
  google: 'providers.google',
  apple: 'providers.apple',
};

/** Google's official "G" logomark, at its minimum on-brand size. */
function GoogleLogo() {
  return (
    <Svg width={18} height={18} viewBox="0 0 18 18">
      <Path
        fill="#4285F4"
        d="M17.64 9.2045c0-.6381-.0573-1.2518-.1636-1.8409H9v3.4814h4.8436c-.2086 1.125-.8427 2.0782-1.7959 2.7164v2.2581h2.9087c1.7018-1.5668 2.6836-3.874 2.6836-6.615z"
      />
      <Path
        fill="#34A853"
        d="M9 18c2.43 0 4.4673-.806 5.9564-2.1805l-2.9087-2.2581c-.8059.54-1.8368.859-3.0477.859-2.344 0-4.3282-1.5831-5.036-3.7104H.9573v2.3318C2.4382 15.9832 5.4818 18 9 18z"
      />
      <Path
        fill="#FBBC05"
        d="M3.964 10.71c-.18-.54-.2822-1.1168-.2822-1.71s.1023-1.17.2823-1.71V4.9582H.9573A8.9965 8.9965 0 000 9c0 1.4523.3477 2.8268.9573 4.0418L3.964 10.71z"
      />
      <Path
        fill="#EA4335"
        d="M9 3.5795c1.3214 0 2.5077.4541 3.4405 1.346l2.5813-2.5814C13.4632.8918 11.426 0 9 0 5.4818 0 2.4382 2.0168.9573 4.9582L3.964 7.29C4.6718 5.1627 6.656 3.5795 9 3.5795z"
      />
    </Svg>
  );
}

/** Google's light/dark button colours (brand-fixed, not the app's palette). */
const GOOGLE_BUTTON_COLORS = {
  light: { background: '#FFFFFF', border: '#747775', text: '#1F1F1F' },
  dark: { background: '#131314', border: '#8E918F', text: '#E3E3E3' },
} as const;

export function ProviderButtons({
  providers = authConfig.providers,
  enabled = authConfig.oauthEnabled,
  onSelect,
}: ProviderButtonsProps) {
  const theme = useTheme();
  const colorScheme = useActiveColorScheme();
  const { t } = useTranslation();
  const [notice, setNotice] = useState<FormMessageValue | null>(null);

  if (providers.length === 0) return null;

  return (
    <View style={styles.container} testID="provider-buttons">
      {providers.map((provider) => {
        const label = t('providers.continueWith', { provider: t(PROVIDER_LABEL_KEY[provider]) });
        const google = provider === 'google';
        const googleColors = GOOGLE_BUTTON_COLORS[colorScheme];

        return (
          <Pressable
            key={provider}
            testID={`provider-button-${provider}`}
            accessibilityRole="button"
            accessibilityLabel={label}
            accessibilityState={{ disabled: !enabled }}
            onPress={() => {
              if (!enabled) {
                setNotice({ kind: 'info', message: 'providers.comingSoon' });
                return;
              }
              onSelect?.(provider);
            }}
            style={({ pressed }) => [
              styles.button,
              google
                ? { borderColor: googleColors.border, backgroundColor: googleColors.background }
                : { borderColor: theme.border, backgroundColor: theme.background },
              !enabled && styles.inactive,
              pressed && styles.pressed,
            ]}>
            {google ? <GoogleLogo /> : null}
            <ThemedText
              type="smallBold"
              style={{ color: google ? googleColors.text : theme.text }}>
              {label}
            </ThemedText>
          </Pressable>
        );
      })}
      <FormMessage message={notice} testID="provider-buttons-notice" />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { gap: Spacing.two },
  button: {
    minHeight: 48,
    borderRadius: 10,
    borderWidth: StyleSheet.hairlineWidth * 2,
    paddingHorizontal: Spacing.four,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: Spacing.two,
  },
  inactive: { opacity: 0.5 },
  pressed: { opacity: 0.7 },
});
