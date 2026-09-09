/**
 * Third-party sign-in buttons — one per configured provider.
 */
import { useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { authConfig, type OAuthProvider } from '@/auth/config';
import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import { useTranslation } from '@/i18n/provider';

import { FormMessage, type FormMessageValue } from './form-message';

export type ProviderButtonsProps = {
  /** Providers to show, in order. Defaults to `authConfig.providers`. */
  providers?: OAuthProvider[];
  enabled?: boolean;
  onSelect?: (provider: OAuthProvider) => void;
};

const PROVIDER_LABEL_KEY: Record<OAuthProvider, 'providers.google' | 'providers.apple'> = {
  google: 'providers.google',
  apple: 'providers.apple',
};

export function ProviderButtons({
  providers = authConfig.providers,
  enabled = authConfig.oauthEnabled,
  onSelect,
}: ProviderButtonsProps) {
  const theme = useTheme();
  const { t } = useTranslation();
  const [notice, setNotice] = useState<FormMessageValue | null>(null);

  if (providers.length === 0) return null;

  return (
    <View style={styles.container} testID="provider-buttons">
      {providers.map((provider) => {
        const label = t('providers.continueWith', { provider: t(PROVIDER_LABEL_KEY[provider]) });
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
              { borderColor: theme.border, backgroundColor: theme.background },
              !enabled && styles.inactive,
              pressed && styles.pressed,
            ]}>
            <ThemedText type="smallBold" style={{ color: theme.text }}>
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
    alignItems: 'center',
    justifyContent: 'center',
  },
  inactive: { opacity: 0.5 },
  pressed: { opacity: 0.7 },
});
