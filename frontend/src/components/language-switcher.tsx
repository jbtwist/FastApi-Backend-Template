/**
 * Segmented picker over `SUPPORTED_LOCALES`, persisting the choice through
 * `setLocale`.
 *
 * Mounted on web only: a browser's language list is a global setting a visitor
 * won't change for one site, so the app has to offer the choice itself. Native
 * follows the device language, which the user already controls per-app in the
 * OS settings.
 */
import { Pressable, StyleSheet, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import { LOCALE_LABELS, SUPPORTED_LOCALES } from '@/i18n';
import { useTranslation } from '@/i18n/provider';

export function LanguageSwitcher() {
  const theme = useTheme();
  const { t, locale, setLocale } = useTranslation();

  return (
    <View
      testID="language-switcher"
      accessibilityRole="radiogroup"
      accessibilityLabel={t('common.language')}
      style={[styles.group, { borderColor: theme.border }]}>
      {SUPPORTED_LOCALES.map((code) => {
        const selected = code === locale;
        return (
          <Pressable
            key={code}
            accessibilityRole="radio"
            accessibilityLabel={LOCALE_LABELS[code]}
            accessibilityState={{ checked: selected, selected }}
            onPress={() => {
              if (!selected) void setLocale(code);
            }}
            style={({ pressed }) => [
              styles.option,
              selected && { backgroundColor: theme.backgroundSelected },
              pressed && styles.pressed,
            ]}>
            <ThemedText type="small" themeColor={selected ? 'text' : 'textSecondary'}>
              {LOCALE_LABELS[code]}
            </ThemedText>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  group: {
    flexDirection: 'row',
    alignItems: 'center',
    alignSelf: 'flex-start',
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: Spacing.three,
    padding: Spacing.half,
    gap: Spacing.half,
  },
  option: {
    paddingVertical: Spacing.one,
    paddingHorizontal: Spacing.two,
    borderRadius: Spacing.two,
  },
  pressed: {
    opacity: 0.7,
  },
});
