/**
 * Segmented picker over `COLOR_SCHEMES`, persisting the choice through
 * `setScheme`.
 *
 * It offers light and dark only. Before any choice the app follows the device,
 * and the option matching what is currently on screen shows as selected — so
 * the control always describes the visible theme, and pressing that same option
 * simply pins it.
 */
import { Pressable, StyleSheet, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import { useTranslation } from '@/i18n/provider';
import type { TranslationKey } from '@/i18n/types';
import { COLOR_SCHEMES, type ColorScheme } from '@/theme/config';
import { useColorSchemeChoice } from '@/theme/provider';

const SCHEME_LABEL_KEY: Record<ColorScheme, TranslationKey> = {
  light: 'common.themeLight',
  dark: 'common.themeDark',
};

export function ThemeSwitcher() {
  const theme = useTheme();
  const { t } = useTranslation();
  const { scheme, setScheme } = useColorSchemeChoice();

  return (
    <View
      testID="theme-switcher"
      accessibilityRole="radiogroup"
      accessibilityLabel={t('common.theme')}
      style={[styles.group, { borderColor: theme.border }]}>
      {COLOR_SCHEMES.map((code) => {
        const selected = code === scheme;
        const label = t(SCHEME_LABEL_KEY[code]);
        return (
          <Pressable
            key={code}
            accessibilityRole="radio"
            accessibilityLabel={label}
            accessibilityState={{ checked: selected, selected }}
            onPress={() => {
              if (!selected) void setScheme(code);
            }}
            style={({ pressed }) => [
              styles.option,
              selected && { backgroundColor: theme.backgroundSelected },
              pressed && styles.pressed,
            ]}>
            <ThemedText type="small" themeColor={selected ? 'text' : 'textSecondary'}>
              {label}
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
